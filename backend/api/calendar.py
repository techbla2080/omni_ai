"""
OmniAI Calendar API Router
Handles Google Calendar OAuth (#29), event read (#30), event create (#31),
and free-slot suggestions (#33).
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
)
from database.database import get_db

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
# #31 — Event Creation Endpoint
# ============================================================

@router.post("/events")
async def create_calendar_event(
    request: Request,
    body: CreateEventRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new calendar event"""
    user_id = await get_user_id(request, db)
    tokens = await get_calendar_tokens(user_id, db)

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
        return {"success": True, "event": event}
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