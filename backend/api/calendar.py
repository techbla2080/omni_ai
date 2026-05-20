"""
OmniAI Calendar API Router
Handles Google Calendar OAuth (#29), event read (#30), event create (#31),
free-slot suggestions (#33), conflict detection (#35), and AI reasoning (#36).
"""

import json
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from services.calendar_service import (
    exchange_code_for_tokens,
    get_user_email,
    fetch_events,
    create_event,
    find_free_slots,
    check_conflicts,
    analyze_calendar,
)
from database.database import get_db
from api.pro_gate import require_pro
from utils.rate_limit import limiter

logger = logging.getLogger(__name__)


# ============================================================
# Request/Response Models
# ============================================================

class CreateEventRequest(BaseModel):
    summary: str
    start: str
    end: str
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    add_meet: bool = False
    timezone: str = "Asia/Kolkata"
    # #35 — When False (default), the create endpoint will check for overlapping
    # events first and return 409 Conflict if any are found. Set to True to
    # bypass the check and create the event anyway (e.g., user clicked
    # "Create anyway" on the conflict warning modal).
    force_create: bool = False


class CheckConflictsRequest(BaseModel):
    """#35 — Lets the frontend preview conflicts before attempting to create."""
    start: str
    end: str
    exclude_event_id: Optional[str] = None
    timezone: str = "Asia/Kolkata"


class AnalyzeCalendarRequest(BaseModel):
    """
    #36 — Calendar AI reasoning request body.

    Frontend POSTs this when the classifier returns action='ask_about_calendar'.
    Backend pulls the user's events for the given range, computes structural
    facts, and hands the whole bundle to Groq with the calendar-advisor prompt.
    Returns prose insight + the raw facts.
    """
    question: str
    range: Optional[str] = "week"  # today | tomorrow | week | month
    start: Optional[str] = None    # optional explicit ISO override
    end: Optional[str] = None      # optional explicit ISO override
    timezone: str = "Asia/Kolkata"


router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


# ============================================================
# Helpers
# ============================================================

async def get_user_id(request: Request, db: AsyncSession) -> str:
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    return user_id


async def get_calendar_tokens(user_id: str, db: AsyncSession) -> dict:
    result = await db.execute(
        text("SELECT calendar_tokens FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    row = result.fetchone()
    if not row or not row[0]:
        raise HTTPException(
            status_code=400,
            detail="Calendar not connected. Please connect your Google Calendar first."
        )
    tokens = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return tokens


# ============================================================
# OAuth Endpoints
# ============================================================

@router.get("/connect")
async def connect_calendar(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Start Calendar OAuth flow"""
    try:
        user_id = await get_user_id(request, db)

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if not token:
            token = request.cookies.get("access_token", "")

        from services.calendar_service import get_oauth_flow
        flow = get_oauth_flow()
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=token
        )
        return {"auth_url": auth_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Calendar auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def calendar_callback(
    code: str = Query(...),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Handle Calendar OAuth callback"""
    if error:
        return RedirectResponse(url=f"/?calendar_error={error}")

    try:
        tokens = exchange_code_for_tokens(code)
        calendar_email = get_user_email(tokens)
        logger.info(f"Calendar connected for: {calendar_email}")

        if state:
            try:
                from jose import jwt
                from utils.config import settings

                payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
                user_id = payload.get("sub")

                if user_id:
                    tokens_json = json.dumps(tokens)
                    await db.execute(
                        text("UPDATE users SET calendar_tokens = :tokens, calendar_email = :email WHERE id = :user_id"),
                        {"tokens": tokens_json, "email": calendar_email, "user_id": user_id}
                    )
                    await db.commit()
                    logger.info(f"Calendar tokens saved for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving calendar tokens from state: {e}")

        return RedirectResponse(
            url=f"/?calendar_connected=true&calendar_email={calendar_email}"
        )
    except Exception as e:
        logger.error(f"Calendar callback error: {e}")
        return RedirectResponse(url=f"/?calendar_error=callback_failed")


@router.get("/status")
async def calendar_status(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Check if Calendar is connected for current user"""
    try:
        user_id = await get_user_id(request, db)
        result = await db.execute(
            text("SELECT calendar_tokens, calendar_email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        row = result.fetchone()
        if row and row[0]:
            return {"connected": True, "email": row[1] or "Connected"}
        return {"connected": False}
    except HTTPException:
        return {"connected": False}
    except Exception as e:
        logger.error(f"Error checking Calendar status: {e}")
        return {"connected": False}


@router.delete("/disconnect")
async def disconnect_calendar(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Disconnect Calendar from user account"""
    try:
        user_id = await get_user_id(request, db)
        await db.execute(
            text("UPDATE users SET calendar_tokens = NULL, calendar_email = NULL WHERE id = :user_id"),
            {"user_id": user_id}
        )
        await db.commit()
        return {"success": True, "message": "Calendar disconnected"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# #30 — Event Reading Endpoint
# ============================================================

@router.get("/events")
async def get_events(
    request: Request,
    range: Optional[str] = Query(None, description="Preset range: today, tomorrow, week, month"),
    start: Optional[str] = Query(None, description="Custom start (ISO 8601)"),
    end: Optional[str] = Query(None, description="Custom end (ISO 8601)"),
    max_results: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Fetch calendar events"""
    from datetime import datetime, timedelta, timezone

    user_id = await get_user_id(request, db)
    tokens = await get_calendar_tokens(user_id, db)

    time_min = start
    time_max = end

    if range and not (start or end):
        now = datetime.now(timezone.utc)
        if range == "today":
            time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            time_max = now.replace(hour=23, minute=59, second=59).isoformat()
        elif range == "tomorrow":
            tomorrow = now + timedelta(days=1)
            time_min = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            time_max = tomorrow.replace(hour=23, minute=59, second=59).isoformat()
        elif range == "week":
            time_min = now.isoformat()
            time_max = (now + timedelta(days=7)).isoformat()
        elif range == "month":
            time_min = now.isoformat()
            time_max = (now + timedelta(days=30)).isoformat()

    try:
        events = fetch_events(
            tokens,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results
        )
        return {
            "events": events,
            "count": len(events),
            "range": range,
            "time_min": time_min,
            "time_max": time_max
        }
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# #31 — Event Creation Endpoint  (with #35 conflict detection)
# ============================================================

@router.post("/events")
@limiter.limit("30/hour")
async def create_calendar_event(
    request: Request,
    body: CreateEventRequest,
    db: AsyncSession = Depends(get_db),
    _pro: None = Depends(require_pro("calendar_create")),
):
    """
    Create a new calendar event.

    #35 — If `force_create` is False (default) and the proposed time window
    overlaps with one or more existing events, this endpoint returns
    HTTP 409 Conflict with a `conflicts` list describing the overlapping events.
    The frontend should show a warning UI; if the user chooses to proceed,
    re-call this endpoint with the same payload plus `force_create=true`.
    """
    user_id = await get_user_id(request, db)
    tokens = await get_calendar_tokens(user_id, db)

    # ---------- #35 — Conflict pre-check ----------
    if not body.force_create:
        try:
            conflicts = check_conflicts(
                tokens,
                start=body.start,
                end=body.end,
                timezone_str=body.timezone
            )
        except ValueError as ve:
            # Bad input (e.g., end before start, invalid ISO time)
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            # Don't block event creation if the conflict check itself fails
            # — log it and continue. Better to risk a duplicate than silently
            # refuse to create the event for an unrelated reason.
            logger.error(f"Conflict check failed (continuing anyway): {e}")
            conflicts = []

        if conflicts:
            logger.info(
                f"Blocking event creation due to {len(conflicts)} conflict(s); "
                f"frontend should show warning to user {user_id}"
            )
            # 409 Conflict — semantically correct status code for this case
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Found {len(conflicts)} conflicting event(s)",
                    "conflicts": conflicts,
                    "proposed": {
                        "summary": body.summary,
                        "start": body.start,
                        "end": body.end
                    }
                }
            )

    # ---------- Create the event ----------
    try:
        event = create_event(
            tokens,
            summary=body.summary,
            start=body.start,
            end=body.end,
            description=body.description,
            location=body.location,
            attendees=body.attendees,
            add_meet=body.add_meet,
            timezone_str=body.timezone
        )
        return {
            "success": True,
            "event": event,
            "force_created": body.force_create
        }
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# #33 — Free Slot Suggestions Endpoint
# ============================================================

@router.get("/free-slots")
async def get_free_slots(
    request: Request,
    duration: int = Query(30, ge=15, le=480, description="Slot duration in minutes (15-480)"),
    range: Optional[str] = Query("week", description="Preset: today, tomorrow, week, month"),
    start: Optional[str] = Query(None, description="Custom start (ISO 8601)"),
    end: Optional[str] = Query(None, description="Custom end (ISO 8601)"),
    max_suggestions: int = Query(10, ge=1, le=20),
    timezone: str = Query("Asia/Kolkata"),
    db: AsyncSession = Depends(get_db)
):
    """
    Find free time slots in the user's calendar.
    Scans 24/7 (no working hours imposed) and returns rounded slot suggestions.

    Usage:
        GET /free-slots?duration=30&range=week
        GET /free-slots?duration=60&range=tomorrow
        GET /free-slots?duration=45&start=2026-04-25T00:00:00%2B05:30&end=2026-04-30T23:59:59%2B05:30
    """
    from datetime import datetime, timedelta, timezone as tz

    user_id = await get_user_id(request, db)
    tokens = await get_calendar_tokens(user_id, db)

    time_min = start
    time_max = end

    if range and not (start or end):
        now = datetime.now(tz.utc)
        if range == "today":
            time_min = now.isoformat()
            time_max = now.replace(hour=23, minute=59, second=59).isoformat()
        elif range == "tomorrow":
            tomorrow = now + timedelta(days=1)
            time_min = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            time_max = tomorrow.replace(hour=23, minute=59, second=59).isoformat()
        elif range == "week":
            time_min = now.isoformat()
            time_max = (now + timedelta(days=7)).isoformat()
        elif range == "month":
            time_min = now.isoformat()
            time_max = (now + timedelta(days=30)).isoformat()

    if not time_min or not time_max:
        raise HTTPException(status_code=400, detail="Provide either 'range' or both 'start' and 'end'.")

    try:
        slots = find_free_slots(
            tokens,
            time_min=time_min,
            time_max=time_max,
            duration_minutes=duration,
            max_suggestions=max_suggestions,
            timezone_str=timezone
        )
        return {
            "slots": slots,
            "count": len(slots),
            "duration_minutes": duration,
            "range": range,
            "time_min": time_min,
            "time_max": time_max
        }
    except Exception as e:
        logger.error(f"Error finding free slots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# #35 — Conflict Detection Endpoint
# ============================================================

@router.post("/check-conflicts")
async def check_event_conflicts(
    request: Request,
    body: CheckConflictsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Preview conflicts for a proposed event time window WITHOUT creating anything.

    Used by the frontend to show a warning modal before the user commits to
    creating an event. The `POST /events` endpoint also runs this check
    internally — this endpoint exists so the frontend can preview conflicts
    proactively (e.g., the moment the user finishes choosing a time, before
    they hit "Create").

    Body:
        start: ISO 8601 start time of the proposed event
        end:   ISO 8601 end time of the proposed event
        exclude_event_id: optional — when editing an existing event, pass its
                          ID so it isn't flagged as conflicting with itself
        timezone: defaults to Asia/Kolkata

    Returns:
        {
          "has_conflicts": bool,
          "count": int,
          "conflicts": [...]  # see services.calendar_service.check_conflicts
        }
    """
    user_id = await get_user_id(request, db)
    tokens = await get_calendar_tokens(user_id, db)

    try:
        conflicts = check_conflicts(
            tokens,
            start=body.start,
            end=body.end,
            exclude_event_id=body.exclude_event_id,
            timezone_str=body.timezone
        )
        return {
            "has_conflicts": len(conflicts) > 0,
            "count": len(conflicts),
            "conflicts": conflicts
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error checking conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# #36 — AI Calendar Reasoning Endpoint
# ============================================================

@router.post("/analyze")
async def analyze_user_calendar(
    request: Request,
    body: AnalyzeCalendarRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calendar AI reasoning. The classifier (#33.5) routes ask_about_calendar
    intents here — questions like "am I overbooked?", "how's my week?",
    "when can I do deep work?", "kal busy hu kya?".

    The pipeline:
      1. Fetch the user's events for the range
      2. Compute structural facts (gaps, density, back-to-back streaks,
         longest free window, per-day breakdown)
      3. Send everything to Groq Llama 3.3 70B with the calendar-advisor prompt
      4. Return prose insight + the raw facts (so the frontend can also show
         structured stats if it wants)

    On Groq failure, returns a deterministic fallback summary so the user
    never sees a 500 — they get useful info either way.

    Body:
        question: User's natural-language question
        range:    "today" | "tomorrow" | "week" | "month" (default "week")
        start, end: optional explicit ISO range (overrides range)
        timezone: defaults to Asia/Kolkata

    Returns:
        {
          "response": str,        # AI advisor prose
          "facts": dict,          # structural facts
          "events_count": int,
          "range": str
        }
    """
    user_id = await get_user_id(request, db)
    tokens = await get_calendar_tokens(user_id, db)

    # Validate range value
    valid_ranges = ("today", "tomorrow", "week", "month")
    range_label = body.range if body.range in valid_ranges else "week"

    # Question is required and shouldn't be empty
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(
            status_code=400,
            detail="Field 'question' is required and cannot be empty."
        )

    try:
        result = await analyze_calendar(
            tokens,
            question=question,
            range_label=range_label,
            time_min=body.start,
            time_max=body.end,
            timezone_str=body.timezone
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in analyze_user_calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))