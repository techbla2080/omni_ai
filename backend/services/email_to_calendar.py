"""
#39 — Email → Calendar Bridge

The killer demo feature. User reads an email thread → clicks "Book Meeting" →
OmniAI extracts attendees + topic from the thread, finds 3 free slots in the
user's calendar, lets them pick one, creates the event with attendees invited
and a Google Meet link.

Architecture (3 functions):
    extract_meeting_intent(thread)       — Groq parses thread for title/duration/urgency
    propose_meeting_slots(token, dur)    — wraps existing find_free_slots
    create_meeting_from_email(...)       — wraps existing create_event with thread context

Why this serves the core thesis:
    Every AI assistant either reads email OR books meetings. OmniAI does both
    as a single bridge action — that's the integration moat.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

import httpx

# Reuse existing services — no rewrites
from services.gmail_service import get_thread_by_id
from services.calendar_service import find_free_slots, create_event

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Defaults locked per #39 architecture decisions — keep simple, predictable
DEFAULT_MEETING_DURATION = 30  # minutes
DEFAULT_SLOT_RANGE = "week"    # next 7 days
DEFAULT_MAX_SLOTS = 3          # show top 3 suggestions
DEFAULT_TIMEZONE = "Asia/Kolkata"


# ============================================================================
# Intent extraction — Groq parses email thread for meeting context
# ============================================================================

INTENT_EXTRACTION_PROMPT = """You analyze email threads to determine if a meeting is being requested or discussed, and extract key meeting parameters.

Read the email thread below. Output STRICT JSON with these fields:

{
  "should_meet": true | false,
  "suggested_title": "string — short meeting title (max 60 chars)",
  "duration_minutes": 15 | 30 | 45 | 60 | 90 | 120,
  "urgency": "low" | "medium" | "high",
  "topic_summary": "string — 1-2 sentences describing what the meeting is about",
  "decline_reason": "string or null — if should_meet is false, why"
}

Rules:
- "should_meet": true only if the thread explicitly or implicitly proposes/needs a meeting (sync, call, discussion, review, catch-up, demo). False for newsletters, automated emails, FYI-only threads.
- "suggested_title": pulled from email subject if relevant, otherwise distilled from content. NEVER include "Re:" or "Fwd:" prefixes. Keep it human and short.
- "duration_minutes": default 30 unless the thread strongly implies otherwise. Quick syncs = 15-30. Demo/review = 30-45. Deep workshop = 60-120.
- "urgency": "high" if explicit urgency signals (ASAP, today, urgent, blocking). "medium" for "this week" / "soon". "low" for "sometime" / "next week".
- "topic_summary": be concrete. "Discuss Q3 marketing budget revisions" not "Talk about something".

Output ONLY the JSON. No prose, no markdown fences."""


async def _call_groq_for_extraction(thread_text: str) -> Dict[str, Any]:
    """Call Groq to extract meeting intent. Always returns a usable dict."""
    if not GROQ_API_KEY:
        logger.warning("#39 GROQ_API_KEY missing — using fallback intent")
        return _fallback_intent("Meeting", "Extracted without AI (no API key)")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": INTENT_EXTRACTION_PROMPT},
                        {"role": "user", "content": thread_text}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 400,
                    "response_format": {"type": "json_object"}
                }
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            return {
                "should_meet": bool(parsed.get("should_meet", True)),
                "suggested_title": (parsed.get("suggested_title") or "Meeting")[:60],
                "duration_minutes": _validate_duration(parsed.get("duration_minutes", DEFAULT_MEETING_DURATION)),
                "urgency": parsed.get("urgency", "medium") if parsed.get("urgency") in ("low", "medium", "high") else "medium",
                "topic_summary": (parsed.get("topic_summary") or "")[:300],
                "decline_reason": parsed.get("decline_reason"),
            }
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"#39 Groq extraction failed: {e}")
        return _fallback_intent("Meeting", f"AI extraction error: {type(e).__name__}")
    except Exception as e:
        logger.warning(f"#39 Groq extraction unexpected error: {e}")
        return _fallback_intent("Meeting", f"Unexpected error: {type(e).__name__}")


def _validate_duration(d: Any) -> int:
    """Clamp duration to an allowed value, default 30."""
    try:
        d = int(d)
    except (TypeError, ValueError):
        return DEFAULT_MEETING_DURATION
    if d in (15, 30, 45, 60, 90, 120):
        return d
    if d < 22:
        return 15
    if d < 37:
        return 30
    if d < 52:
        return 45
    if d < 75:
        return 60
    if d < 105:
        return 90
    return 120


def _fallback_intent(title: str, note: str) -> Dict[str, Any]:
    """Safe default when AI extraction is unavailable."""
    return {
        "should_meet": True,
        "suggested_title": title,
        "duration_minutes": DEFAULT_MEETING_DURATION,
        "urgency": "medium",
        "topic_summary": "",
        "decline_reason": note,
    }


def _build_thread_text_for_ai(
    thread: Dict[str, Any],
    max_messages: int = 5,
    max_chars_per_msg: int = 1500
) -> str:
    """Format thread into clean text for the AI to read."""
    parts = [f"Subject: {thread.get('subject', '(no subject)')}"]
    parts.append(f"Total messages: {thread.get('message_count', 0)}")
    parts.append("---")

    msgs = thread.get("messages", [])
    if len(msgs) > max_messages:
        msgs = msgs[-max_messages:]
        parts.append(f"(Showing last {max_messages} messages)")
        parts.append("---")

    for i, m in enumerate(msgs, 1):
        body = m.get("body", "") or m.get("snippet", "")
        if len(body) > max_chars_per_msg:
            body = body[:max_chars_per_msg] + "... [truncated]"
        parts.append(f"Message {i} of {len(msgs)}")
        parts.append(f"From: {m.get('from', '')}")
        if m.get("to"):
            parts.append(f"To: {m['to']}")
        parts.append(f"Date: {m.get('date', '')}")
        parts.append("")
        parts.append(body)
        parts.append("---")

    return "\n".join(parts)


# ============================================================================
# Public API — these are what the route handler calls
# ============================================================================

async def extract_meeting_intent(thread: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a full thread dict from gmail_service.get_thread_by_id, extract
    meeting parameters via Groq. Always returns a usable dict — never raises.

    Output shape:
        {
            "should_meet": bool,
            "suggested_title": str,
            "duration_minutes": int,
            "urgency": "low" | "medium" | "high",
            "topic_summary": str,
            "decline_reason": str | None,
            "suggested_attendees": [{"name", "email", "role"}],
            "thread_subject": str
        }
    """
    if not thread or not thread.get("messages"):
        return {
            **_fallback_intent("Meeting", "Empty thread"),
            "suggested_attendees": [],
            "thread_subject": "(no subject)"
        }

    thread_text = _build_thread_text_for_ai(thread)
    intent = await _call_groq_for_extraction(thread_text)

    # Build attendee list from thread participants.
    # Per #39 decision 3: include sender + To + CC, exclude self.
    user_email_lower = (thread.get("_current_user_email") or "").lower()
    suggested_attendees = []
    for p in thread.get("participants", []):
        email = p.get("email", "").lower()
        if not email or email == user_email_lower:
            continue
        suggested_attendees.append({
            "name": p.get("name") or email.split("@")[0],
            "email": email,
            "role": p.get("role", "to")
        })

    intent["suggested_attendees"] = suggested_attendees
    intent["thread_subject"] = thread.get("subject", "(no subject)")
    return intent


def propose_meeting_slots(
    calendar_token_data: Dict[str, Any],
    duration_minutes: int = DEFAULT_MEETING_DURATION,
    range_label: str = DEFAULT_SLOT_RANGE,
    max_suggestions: int = DEFAULT_MAX_SLOTS,
    timezone_str: str = DEFAULT_TIMEZONE
) -> List[Dict[str, Any]]:
    """
    Find free slots in the user's calendar matching #39's defaults.

    Thin wrapper around find_free_slots so #39's slot-finding policy lives
    in one place. Returns empty list on any error (caller falls back).
    """
    try:
        slots = find_free_slots(
            token_data=calendar_token_data,
            duration_minutes=duration_minutes,
            range_label=range_label,
            max_suggestions=max_suggestions,
            timezone_str=timezone_str
        )
        return slots or []
    except TypeError as e:
        # find_free_slots signature mismatch — try positional call
        logger.warning(f"#39 find_free_slots kwargs mismatch: {e}. Trying positional.")
        try:
            slots = find_free_slots(
                calendar_token_data,
                duration_minutes,
                range_label
            )
            return (slots or [])[:max_suggestions]
        except Exception as e2:
            logger.error(f"#39 propose_meeting_slots fallback failed: {e2}")
            return []
    except Exception as e:
        logger.error(f"#39 propose_meeting_slots error: {e}")
        return []


def create_meeting_from_email(
    calendar_token_data: Dict[str, Any],
    title: str,
    start_iso: str,
    end_iso: str,
    attendees: List[str],
    thread_subject: str = "",
    thread_id: Optional[str] = None,
    topic_summary: str = "",
    add_meet: bool = True,
    timezone_str: str = DEFAULT_TIMEZONE
) -> Dict[str, Any]:
    """
    Create a calendar event from email context. Wraps existing create_event()
    but enriches the description with thread reference + topic summary so the
    invite recipients have context about WHY this meeting was scheduled.

    Returns the event dict from create_event, or {"error": ...} on failure.
    """
    description_parts = []

    if topic_summary:
        description_parts.append(topic_summary)
        description_parts.append("")

    if thread_subject:
        description_parts.append(f"📧 Booked from email thread: \"{thread_subject}\"")

    if thread_id:
        # Direct link to the original thread in Gmail web UI
        gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
        description_parts.append(f"View thread: {gmail_link}")

    description_parts.append("")
    description_parts.append("— Booked with OmniAI")

    description = "\n".join(description_parts)

    # Attendees come in as plain emails; create_event expects them in this form
    cleaned_attendees = [
        e.strip().lower() for e in (attendees or [])
        if e and "@" in e
    ]

    try:
        event = create_event(
            token_data=calendar_token_data,
            summary=title,
            start=start_iso,
            end=end_iso,
            description=description,
            attendees=cleaned_attendees if cleaned_attendees else None,
            add_meet=add_meet,
            timezone=timezone_str,
            force_create=False  # honor existing #35 conflict pre-check
        )
        return event
    except TypeError as e:
        # Signature mismatch — try without the newer params
        logger.warning(f"#39 create_event kwargs mismatch: {e}. Trying minimal call.")
        try:
            event = create_event(
                calendar_token_data,
                title,
                start_iso,
                end_iso,
                description,
                None,  # location
                cleaned_attendees if cleaned_attendees else None,
                add_meet,
                timezone_str
            )
            return event
        except Exception as e2:
            logger.error(f"#39 create_meeting_from_email fallback failed: {e2}")
            return {"error": f"Could not create event: {e2}"}
    except Exception as e:
        logger.error(f"#39 create_meeting_from_email error: {e}")
        return {"error": str(e)}


# ============================================================================
# Convenience: full workflow in one call (used by the API endpoint)
# ============================================================================

async def prepare_booking_from_thread(
    gmail_token_data: Dict[str, Any],
    calendar_token_data: Dict[str, Any],
    thread_id: str,
    user_email: str,
    duration_override: Optional[int] = None
) -> Dict[str, Any]:
    """
    Convenience function used by the API endpoint to do the "preparation"
    phase in one shot: fetch thread → extract intent → propose slots.

    Returns:
        {
            "ok": True,
            "intent": {...},
            "slots": [...],
            "thread_id": "...",
        }
    OR
        {
            "ok": False,
            "error": "..."
        }
    """
    # Step 1 — Fetch the Gmail thread
    thread = get_thread_by_id(gmail_token_data, thread_id)
    if not thread:
        return {"ok": False, "error": "Could not fetch the email thread."}

    # Pass user email into thread so attendee filtering excludes self
    thread["_current_user_email"] = user_email

    # Step 2 — Extract meeting intent via Groq
    intent = await extract_meeting_intent(thread)

    # Step 3 — Propose slots from user's calendar
    duration = duration_override if duration_override else intent.get("duration_minutes", DEFAULT_MEETING_DURATION)
    duration = _validate_duration(duration)

    slots = propose_meeting_slots(
        calendar_token_data=calendar_token_data,
        duration_minutes=duration,
        range_label=DEFAULT_SLOT_RANGE,
        max_suggestions=DEFAULT_MAX_SLOTS,
    )

    # Update intent with the actual duration we ended up using
    intent["duration_minutes"] = duration

    return {
        "ok": True,
        "intent": intent,
        "slots": slots,
        "thread_id": thread_id,
    }