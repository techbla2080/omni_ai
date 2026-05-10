"""
#39 — Email → Calendar Bridge API endpoints.

Two-step flow for safety:
    POST /api/v1/calendar/book-from-email/prepare
        Read the thread, extract meeting intent via Groq, propose free slots.
        Returns proposals for the user to review.
    
    POST /api/v1/calendar/book-from-email/confirm
        User picked a slot + finalized attendees/title. Create the event.
        Sends Google Calendar invites + adds Meet link + links to thread.

Why two endpoints? The user MUST see what's being proposed before we send
invites to potentially 5 people. Better one click of friction than 14 wrong
calendar invites in someone's CEO's inbox.

Auth: standard JWT pattern via api.auth.get_current_user (matches calendar.py
and gmail.py routes). Both Gmail AND Calendar must be connected for the user
or we return a clear 400 telling them to connect.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db

# Service layer — the actual logic
from services.email_to_calendar import (
    prepare_booking_from_thread,
    create_meeting_from_email,
    DEFAULT_MEETING_DURATION,
    DEFAULT_TIMEZONE,
)
from services.gmail_service import get_user_email as get_gmail_user_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calendar", tags=["email-calendar-bridge"])


# ============================================================================
# Auth + token helpers
# ============================================================================

async def get_user_id(request: Request, db: AsyncSession) -> str:
    """Extract authenticated user_id from JWT. 401 if missing."""
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


async def get_gmail_tokens(user_id: str, db: AsyncSession) -> dict:
    """
    Fetch the user's Gmail OAuth tokens. Mirrors the helper in api/gmail.py
    so we don't create a circular import or have to refactor that file.
    """
    result = await db.execute(
        text("""
            SELECT token_data FROM oauth_tokens
            WHERE user_id = :user_id AND provider = 'gmail'
        """),
        {"user_id": user_id}
    )
    row = result.fetchone()
    if not row or not row[0]:
        return None
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def get_calendar_tokens(user_id: str, db: AsyncSession) -> dict:
    """Fetch the user's Google Calendar OAuth tokens."""
    result = await db.execute(
        text("""
            SELECT token_data FROM oauth_tokens
            WHERE user_id = :user_id AND provider = 'calendar'
        """),
        {"user_id": user_id}
    )
    row = result.fetchone()
    if not row or not row[0]:
        return None
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


# ============================================================================
# Pydantic models
# ============================================================================

class PrepareBookingRequest(BaseModel):
    """Body for POST /book-from-email/prepare"""
    thread_id: str = Field(..., min_length=1, max_length=200)
    duration_override: Optional[int] = Field(
        None,
        description="Override AI-suggested duration in minutes. 15/30/45/60/90/120 supported."
    )


class SuggestedAttendee(BaseModel):
    name: str
    email: str
    role: str  # 'sender' | 'to' | 'cc'


class MeetingIntent(BaseModel):
    """The AI-extracted intent — what kind of meeting this should be."""
    should_meet: bool
    suggested_title: str
    duration_minutes: int
    urgency: str
    topic_summary: str
    decline_reason: Optional[str] = None
    suggested_attendees: List[SuggestedAttendee]
    thread_subject: str


class ProposedSlot(BaseModel):
    """A free time slot from the user's calendar — pass-through from find_free_slots."""
    start: str
    end: str
    day_label: Optional[str] = None
    time_label: Optional[str] = None
    end_time_label: Optional[str] = None
    duration_minutes: Optional[int] = None


class PrepareBookingResponse(BaseModel):
    """Returned by /book-from-email/prepare"""
    intent: MeetingIntent
    slots: List[ProposedSlot]
    thread_id: str
    has_calendar: bool = True
    has_gmail: bool = True


class ConfirmBookingRequest(BaseModel):
    """
    Body for POST /book-from-email/confirm — user has picked a slot and
    optionally edited the title/attendees in the confirmation modal.
    """
    thread_id: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=200)
    start: str = Field(..., description="ISO datetime string from the picked slot")
    end: str = Field(..., description="ISO datetime string from the picked slot")
    attendees: List[str] = Field(default_factory=list, description="Email addresses")
    topic_summary: Optional[str] = Field(None, max_length=500)
    add_meet: bool = True
    timezone: Optional[str] = DEFAULT_TIMEZONE


class ConfirmBookingResponse(BaseModel):
    """Returned by /book-from-email/confirm"""
    success: bool
    event: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============================================================================
# Endpoint 1 — Prepare: read thread, propose meeting
# ============================================================================

@router.post("/book-from-email/prepare", response_model=PrepareBookingResponse)
async def prepare_booking(
    body: PrepareBookingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Step 1 of email→calendar booking: read the email thread, extract meeting
    intent via Groq, find 3 free slots in the user's calendar.
    
    Returns everything the frontend needs to render the confirmation modal:
    suggested title, duration, attendees, and slot picker options.
    
    User flow at this point:
        1. Frontend calls this endpoint
        2. Modal opens with: AI's suggested title (editable), 3 slot buttons,
           attendee chips (deselectable), topic summary
        3. User picks slot, edits as needed, clicks "Book"
        4. Frontend calls /confirm with the final values
    """
    user_id = await get_user_id(request, db)
    
    # Both providers must be connected — this is the bridge feature, after all
    gmail_tokens = await get_gmail_tokens(user_id, db)
    if not gmail_tokens:
        raise HTTPException(
            status_code=400,
            detail="Gmail not connected. Connect your Gmail account first."
        )
    
    calendar_tokens = await get_calendar_tokens(user_id, db)
    if not calendar_tokens:
        raise HTTPException(
            status_code=400,
            detail="Google Calendar not connected. Connect your Calendar first."
        )
    
    # We need the user's own email so attendee filtering excludes self.
    # Use Gmail's getProfile rather than session data — the connected account
    # is the source of truth.
    try:
        user_email = get_gmail_user_email(gmail_tokens)
    except Exception as e:
        logger.warning(f"#39 Could not fetch Gmail user email for {user_id[:8]}: {e}")
        user_email = ""
    
    # Run the full preparation flow in the service layer
    result = await prepare_booking_from_thread(
        gmail_token_data=gmail_tokens,
        calendar_token_data=calendar_tokens,
        thread_id=body.thread_id,
        user_email=user_email,
        duration_override=body.duration_override
    )
    
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Could not prepare booking from this thread.")
        )
    
    # Wrap raw service output in our typed response model
    intent_raw = result["intent"]
    slots_raw = result.get("slots", [])
    
    return PrepareBookingResponse(
        intent=MeetingIntent(
            should_meet=intent_raw.get("should_meet", True),
            suggested_title=intent_raw.get("suggested_title", "Meeting"),
            duration_minutes=intent_raw.get("duration_minutes", DEFAULT_MEETING_DURATION),
            urgency=intent_raw.get("urgency", "medium"),
            topic_summary=intent_raw.get("topic_summary", ""),
            decline_reason=intent_raw.get("decline_reason"),
            suggested_attendees=[
                SuggestedAttendee(
                    name=a.get("name", ""),
                    email=a.get("email", ""),
                    role=a.get("role", "to")
                )
                for a in intent_raw.get("suggested_attendees", [])
            ],
            thread_subject=intent_raw.get("thread_subject", "(no subject)")
        ),
        slots=[
            ProposedSlot(
                start=s.get("start", ""),
                end=s.get("end", ""),
                day_label=s.get("day_label"),
                time_label=s.get("time_label"),
                end_time_label=s.get("end_time_label"),
                duration_minutes=s.get("duration_minutes")
            )
            for s in slots_raw
        ],
        thread_id=body.thread_id,
    )


# ============================================================================
# Endpoint 2 — Confirm: create the event
# ============================================================================

@router.post("/book-from-email/confirm", response_model=ConfirmBookingResponse)
async def confirm_booking(
    body: ConfirmBookingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Step 2 of email→calendar booking: user reviewed the proposal and
    confirmed. Create the actual calendar event with attendees + Meet link.
    
    The event description is enriched in the service layer with a link back
    to the original Gmail thread, so attendees know WHY this meeting exists.
    """
    user_id = await get_user_id(request, db)
    
    calendar_tokens = await get_calendar_tokens(user_id, db)
    if not calendar_tokens:
        raise HTTPException(
            status_code=400,
            detail="Google Calendar not connected. Connect your Calendar first."
        )
    
    # Light validation — title shouldn't be empty after stripping
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    
    # Filter attendees to valid emails only
    attendees_clean = [
        e.strip().lower() for e in (body.attendees or [])
        if e and "@" in e
    ]
    
    event = create_meeting_from_email(
        calendar_token_data=calendar_tokens,
        title=title,
        start_iso=body.start,
        end_iso=body.end,
        attendees=attendees_clean,
        thread_subject="",  # caller already wrote a meaningful title
        thread_id=body.thread_id,
        topic_summary=body.topic_summary or "",
        add_meet=body.add_meet,
        timezone_str=body.timezone or DEFAULT_TIMEZONE,
    )
    
    # The service returns either an event dict or {"error": str}
    if isinstance(event, dict) and event.get("error"):
        logger.warning(f"#39 Booking failed for user {user_id[:8]}: {event['error']}")
        return ConfirmBookingResponse(
            success=False,
            error=event["error"]
        )
    
    logger.info(f"#39 User {user_id[:8]} booked meeting from thread {body.thread_id[:12]}")
    return ConfirmBookingResponse(
        success=True,
        event=event if isinstance(event, dict) else None
    )