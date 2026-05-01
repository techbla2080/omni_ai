"""
OmniAI Calendar Service
Handles OAuth2 flow and Google Calendar API calls.
Includes: OAuth (#29), event read (#30), event create (#31), free slots (#33),
conflict detection (#35), AI reasoning (#36).
"""

import os
import logging
from typing import Dict, Any, List, Optional

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv(
    "GOOGLE_CALENDAR_REDIRECT_URI",
    "https://omniai.biz/api/v1/calendar/callback"
)


def get_oauth_flow() -> Flow:
    """Create OAuth2 flow for Calendar"""
    # Suppress strict scope validation — Google may return extra granted scopes
    # (e.g., Gmail) when include_granted_scopes=true is used
    import os as _os
    _os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return flow


def get_auth_url() -> str:
    """Get the Google OAuth authorization URL for Calendar"""
    flow = get_oauth_flow()
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for tokens"""
    flow = get_oauth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None
    }


def get_calendar_service(token_data: Dict[str, Any]):
    """Build authenticated Google Calendar service object"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from datetime import datetime

    expiry = None
    if token_data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(token_data["expiry"])
        except Exception:
            expiry = None

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id", CLIENT_ID),
        client_secret=token_data.get("client_secret", CLIENT_SECRET),
        scopes=token_data.get("scopes", SCOPES),
        expiry=expiry
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build('calendar', 'v3', credentials=creds, cache_discovery=False)


def get_user_email(token_data: Dict[str, Any]) -> str:
    """Fetch the connected Google account email using the OAuth userinfo endpoint"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import AuthorizedSession

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id", CLIENT_ID),
            client_secret=token_data.get("client_secret", CLIENT_SECRET),
            scopes=token_data.get("scopes", SCOPES)
        )
        session = AuthorizedSession(creds)
        resp = session.get("https://www.googleapis.com/oauth2/v2/userinfo")
        if resp.status_code == 200:
            return resp.json().get("email", "")
    except Exception as e:
        logger.error(f"Error fetching user email: {e}")
    return ""


def fetch_events(token_data: Dict[str, Any],
                  time_min: str = None,
                  time_max: str = None,
                  max_results: int = 20) -> list:
    """
    Fetch calendar events from the user's primary calendar.
    Returns normalized list of event dicts.
    """
    from datetime import datetime, timedelta, timezone

    service = get_calendar_service(token_data)

    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()
    if not time_max:
        time_max = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        normalized = []
        for event in events:
            start = event.get('start', {})
            end = event.get('end', {})

            is_all_day = 'date' in start
            start_time = start.get('dateTime') or start.get('date', '')
            end_time = end.get('dateTime') or end.get('date', '')

            attendees_list = []
            for attendee in event.get('attendees', []):
                attendees_list.append({
                    'email': attendee.get('email', ''),
                    'name': attendee.get('displayName', ''),
                    'response': attendee.get('responseStatus', 'needsAction'),
                    'is_organizer': attendee.get('organizer', False)
                })

            meet_link = None
            conference = event.get('conferenceData', {})
            if conference:
                for entry in conference.get('entryPoints', []):
                    if entry.get('entryPointType') == 'video':
                        meet_link = entry.get('uri')
                        break

            normalized.append({
                'id': event.get('id', ''),
                'summary': event.get('summary', '(no title)'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'start': start_time,
                'end': end_time,
                'is_all_day': is_all_day,
                'html_link': event.get('htmlLink', ''),
                'meet_link': meet_link,
                'attendees': attendees_list,
                'status': event.get('status', 'confirmed'),
                'organizer_email': event.get('organizer', {}).get('email', ''),
                'created': event.get('created', ''),
                'updated': event.get('updated', '')
            })

        return normalized

    except HttpError as e:
        logger.error(f"Calendar API error in fetch_events: {e}")
        raise


def get_events_count_for_range(token_data: Dict[str, Any], days: int = 7) -> int:
    """Quick helper: count of events in the next N days"""
    from datetime import datetime, timedelta, timezone

    time_min = datetime.now(timezone.utc).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    try:
        events = fetch_events(token_data, time_min=time_min, time_max=time_max, max_results=50)
        return len(events)
    except Exception as e:
        logger.error(f"Error counting events: {e}")
        return 0


def create_event(token_data: Dict[str, Any],
                  summary: str,
                  start: str,
                  end: str,
                  description: str = None,
                  location: str = None,
                  attendees: list = None,
                  add_meet: bool = False,
                  timezone_str: str = "Asia/Kolkata") -> Dict[str, Any]:
    """
    Create a new event on the user's primary Google Calendar.
    """
    service = get_calendar_service(token_data)

    is_all_day = 'T' not in start
    start_field = {'date': start} if is_all_day else {'dateTime': start, 'timeZone': timezone_str}
    end_field = {'date': end} if is_all_day else {'dateTime': end, 'timeZone': timezone_str}

    event_body = {
        'summary': summary,
        'start': start_field,
        'end': end_field,
    }

    if description:
        event_body['description'] = description
    if location:
        event_body['location'] = location
    if attendees:
        event_body['attendees'] = [{'email': email.strip()} for email in attendees if email and email.strip()]

    conference_data_version = 0
    if add_meet:
        import uuid
        event_body['conferenceData'] = {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }
        conference_data_version = 1

    try:
        created = service.events().insert(
            calendarId='primary',
            body=event_body,
            conferenceDataVersion=conference_data_version,
            sendUpdates='all' if attendees else 'none'
        ).execute()

        meet_link = None
        conference = created.get('conferenceData', {})
        if conference:
            for entry in conference.get('entryPoints', []):
                if entry.get('entryPointType') == 'video':
                    meet_link = entry.get('uri')
                    break

        start_obj = created.get('start', {})
        end_obj = created.get('end', {})

        return {
            'id': created.get('id', ''),
            'summary': created.get('summary', ''),
            'description': created.get('description', ''),
            'location': created.get('location', ''),
            'start': start_obj.get('dateTime') or start_obj.get('date', ''),
            'end': end_obj.get('dateTime') or end_obj.get('date', ''),
            'html_link': created.get('htmlLink', ''),
            'meet_link': meet_link,
            'attendees': [{'email': a.get('email', ''), 'response': a.get('responseStatus', '')}
                         for a in created.get('attendees', [])],
            'status': created.get('status', 'confirmed'),
            'created': created.get('created', '')
        }
    except HttpError as e:
        logger.error(f"Calendar API error in create_event: {e}")
        raise


# ============================================================
# #33 — Free Slot Finding
# ============================================================

def find_free_slots(token_data: Dict[str, Any],
                     time_min: str,
                     time_max: str,
                     duration_minutes: int = 30,
                     max_suggestions: int = 10,
                     timezone_str: str = "Asia/Kolkata") -> List[Dict[str, Any]]:
    """
    Find free time slots in the user's calendar within a given range.
    Scans 24/7 — no working hours imposed.

    Args:
        token_data: OAuth tokens
        time_min: ISO 8601 range start (e.g., "2026-04-25T00:00:00+05:30")
        time_max: ISO 8601 range end
        duration_minutes: Required slot length in minutes (default 30)
        max_suggestions: Max number of free slots to return
        timezone_str: Timezone for display

    Returns:
        List of free slot dicts: [{start, end, duration_minutes, day_label}, ...]
    """
    from datetime import datetime, timedelta

    # Fetch events in the range
    try:
        events = fetch_events(token_data, time_min=time_min, time_max=time_max, max_results=50)
    except Exception as e:
        logger.error(f"Error fetching events for free slots: {e}")
        raise

    # Parse range start/end
    try:
        range_start = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
        range_end = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
    except Exception as e:
        logger.error(f"Error parsing time range: {e}")
        raise ValueError(f"Invalid time range: {e}")

    # Build a list of busy intervals (skip all-day events for slot finding)
    busy_intervals = []
    for ev in events:
        if ev.get('is_all_day'):
            continue
        try:
            start = datetime.fromisoformat(ev['start'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(ev['end'].replace('Z', '+00:00'))
            busy_intervals.append((start, end))
        except Exception:
            continue

    # Sort and merge overlapping intervals
    busy_intervals.sort(key=lambda x: x[0])
    merged_busy = []
    for interval in busy_intervals:
        if merged_busy and interval[0] <= merged_busy[-1][1]:
            merged_busy[-1] = (merged_busy[-1][0], max(merged_busy[-1][1], interval[1]))
        else:
            merged_busy.append(interval)

    # Find gaps between busy intervals (= free slots)
    free_slots = []
    cursor = range_start
    duration_delta = timedelta(minutes=duration_minutes)

    for busy_start, busy_end in merged_busy:
        # Gap between cursor and the next busy interval
        if busy_start > cursor:
            gap_duration = busy_start - cursor
            if gap_duration >= duration_delta:
                free_slots.append((cursor, busy_start))
        cursor = max(cursor, busy_end)

    # Final gap from cursor to range_end
    if range_end > cursor:
        gap_duration = range_end - cursor
        if gap_duration >= duration_delta:
            free_slots.append((cursor, range_end))

    # Format slots — split large gaps into rounded suggestion blocks
    suggestions = []
    for slot_start, slot_end in free_slots:
        if len(suggestions) >= max_suggestions:
            break

        # Round to next 15-min boundary
        minute = slot_start.minute
        rounded_minute = ((minute + 14) // 15) * 15
        if rounded_minute >= 60:
            rounded_start = slot_start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            rounded_start = slot_start.replace(minute=rounded_minute, second=0, microsecond=0)

        # If the rounded start + duration fits in the slot, suggest it
        if rounded_start + duration_delta <= slot_end:
            suggested_end = rounded_start + duration_delta
            day_label = rounded_start.strftime('%a, %b %d')
            time_label = rounded_start.strftime('%I:%M %p').lstrip('0')
            end_label = suggested_end.strftime('%I:%M %p').lstrip('0')

            suggestions.append({
                'start': rounded_start.isoformat(),
                'end': suggested_end.isoformat(),
                'duration_minutes': duration_minutes,
                'day_label': day_label,
                'time_label': time_label,
                'end_time_label': end_label,
                'display': f"{day_label} · {time_label} – {end_label}"
            })

    return suggestions


# ============================================================
# #35 — Conflict Detection
# ============================================================

def check_conflicts(token_data: Dict[str, Any],
                     start: str,
                     end: str,
                     exclude_event_id: Optional[str] = None,
                     timezone_str: str = "Asia/Kolkata") -> List[Dict[str, Any]]:
    """
    Check for events that overlap with the given time window.

    Two intervals A and B overlap if and only if:
        A.start < B.end AND A.end > B.start

    This catches all overlap cases: full overlap, partial overlap on either side,
    and one event fully containing the other.

    All-day events are skipped — they would conflict with everything on that day,
    which is rarely the user's intent when scheduling a timed event.

    Args:
        token_data: OAuth tokens
        start: ISO 8601 start time of the proposed new event
        end: ISO 8601 end time of the proposed new event
        exclude_event_id: Optional event ID to exclude from conflict check.
                          Use this when EDITING an existing event so it doesn't
                          conflict with itself.
        timezone_str: Timezone (currently unused — kept for API consistency
                      with create_event)

    Returns:
        List of conflicting event dicts. Empty list = no conflicts (safe to create).
        Each conflict dict contains:
            - id: Google Calendar event ID
            - summary: event title
            - start: ISO 8601 start
            - end: ISO 8601 end
            - location: event location (may be empty)
            - html_link: link to open the event in Google Calendar
            - overlap_type: 'full' | 'partial_start' | 'partial_end' | 'contains' | 'contained'
    """
    from datetime import datetime, timedelta

    # Parse the proposed new event window
    try:
        new_start = datetime.fromisoformat(start.replace('Z', '+00:00'))
        new_end = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except Exception as e:
        logger.error(f"Error parsing proposed event time: {e}")
        raise ValueError(f"Invalid start/end time: {e}")

    if new_end <= new_start:
        raise ValueError("Event end time must be after start time")

    # Fetch events with a small buffer on either side, so we catch events that
    # start before our window or end after our window
    buffer = timedelta(hours=1)
    fetch_min = (new_start - buffer).isoformat()
    fetch_max = (new_end + buffer).isoformat()

    try:
        events = fetch_events(
            token_data,
            time_min=fetch_min,
            time_max=fetch_max,
            max_results=50
        )
    except Exception as e:
        logger.error(f"Error fetching events for conflict check: {e}")
        raise

    conflicts = []
    for ev in events:
        # Skip all-day events — they should not block timed scheduling
        if ev.get('is_all_day'):
            continue

        # Skip the excluded event (used when editing)
        if exclude_event_id and ev.get('id') == exclude_event_id:
            continue

        # Skip cancelled events
        if ev.get('status') == 'cancelled':
            continue

        # Parse this event's window
        try:
            ev_start = datetime.fromisoformat(ev['start'].replace('Z', '+00:00'))
            ev_end = datetime.fromisoformat(ev['end'].replace('Z', '+00:00'))
        except Exception:
            # Skip events with unparseable times rather than crash
            continue

        # The overlap rule: new_start < ev_end AND new_end > ev_start
        if new_start < ev_end and new_end > ev_start:
            # Classify the type of overlap for richer UI later
            if new_start <= ev_start and new_end >= ev_end:
                overlap_type = 'contains'  # new event fully contains existing
            elif ev_start <= new_start and ev_end >= new_end:
                overlap_type = 'contained'  # new event sits fully inside existing
            elif new_start < ev_start:
                overlap_type = 'partial_start'  # new event overlaps the start of existing
            elif new_end > ev_end:
                overlap_type = 'partial_end'  # new event overlaps the end of existing
            else:
                overlap_type = 'full'  # exact match (should be rare)

            # Format human-readable labels for the frontend
            day_label = ev_start.strftime('%a, %b %d')
            time_label = ev_start.strftime('%I:%M %p').lstrip('0')
            end_time_label = ev_end.strftime('%I:%M %p').lstrip('0')

            conflicts.append({
                'id': ev.get('id', ''),
                'summary': ev.get('summary', '(no title)'),
                'start': ev['start'],
                'end': ev['end'],
                'location': ev.get('location', ''),
                'html_link': ev.get('html_link', ''),
                'overlap_type': overlap_type,
                'day_label': day_label,
                'time_label': time_label,
                'end_time_label': end_time_label,
                'display': f"{day_label} · {time_label} – {end_time_label}"
            })

    # Sort conflicts by start time so the UI shows them in order
    conflicts.sort(key=lambda c: c['start'])

    logger.info(
        f"Conflict check: window {start} → {end}, "
        f"found {len(conflicts)} conflict(s)"
    )

    return conflicts


# ============================================================
# #36 — AI Calendar Reasoning
# ============================================================

# System prompt for the calendar advisor LLM call.
# Tuned for concise, specific, proactive responses in the user's language.
ADVISOR_SYSTEM_PROMPT = """You are OmniAI's calendar advisor. The user will ask you a question about their schedule, and you will receive:
1. The user's question
2. Pre-computed structural facts about their calendar (totals, gaps, density, free windows)
3. The raw event list

Your job: answer the question with insight, not just data.

STYLE RULES:
- Keep responses CONCISE — 2 to 5 sentences usually. Never write essays.
- Be SPECIFIC — cite actual event titles and times, not generic statements.
- Be PROACTIVE — suggest, don't just describe. If they ask "am I overbooked?", end with what they could do about it.
- Match the USER'S LANGUAGE — if they wrote in Hindi/Hinglish, respond in Hindi/Hinglish. English question → English response.
- Use natural prose. No headings, no bullet lists unless the question genuinely requires comparing 3+ items.
- Never invent events that aren't in the data. If the calendar is empty, say so plainly.
- Don't lecture about productivity or time management — just answer the question.

WHAT TO PRIORITIZE:
- For "am I overbooked / busy?" → density, back-to-back streaks, longest meeting-free window
- For "when can I do deep work?" → longest free windows, ideally 60+ minutes
- For "summarize my day/week" → headline (busy/light), 2-3 standout events, total hours
- For "compare day X to day Y" → density delta, key differences
- For vague open-ended questions → headline insight + one concrete suggestion

LANGUAGE EXAMPLES:
English question → English response in plain conversational tone
Hindi question ("kal kaisa hai?") → Hindi/Hinglish response ("Kal kaafi packed hai — 4 meetings hain, sirf 30 min ka break hai dopahar 1 baje. Deep work ke liye time nahi milega.")

OUTPUT: just the response prose. No JSON, no markdown headers, no preamble."""


def _format_iso_for_display(iso_str: str, timezone_str: str = "Asia/Kolkata") -> str:
    """Helper: format ISO timestamp as 'Mon, May 04 · 3:00 PM'"""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime('%a, %b %d · %I:%M %p').replace(' 0', ' ')
    except Exception:
        return iso_str


def compute_calendar_facts(events: List[Dict[str, Any]],
                            range_label: str = "week",
                            timezone_str: str = "Asia/Kolkata") -> Dict[str, Any]:
    """
    Compute structural facts from a list of events. These facts are fed to the
    LLM advisor alongside the raw events, dramatically improving response
    quality (LLMs are bad at counting hours / minutes / detecting back-to-back
    streaks; we do that math here and let the LLM focus on natural-language
    reasoning).

    Args:
        events: Normalized event list from fetch_events()
        range_label: "today" | "tomorrow" | "week" | "month" — for context only
        timezone_str: User's timezone

    Returns:
        Dict with:
            total_events: int
            timed_events: int (excluding all-day)
            all_day_events: int
            total_minutes_booked: int  (sum of timed event durations)
            total_hours_booked: float
            longest_meeting: dict | None  ({summary, duration_minutes, start})
            shortest_meeting: dict | None
            longest_free_window: dict | None  ({start, end, duration_minutes})
            free_windows_60min_or_more: list of dicts (top 5)
            back_to_back_streaks: list of dicts ({count, start, end})
                                   — runs of 3+ consecutive meetings with <15min gaps
            density_score: float  (0.0 = empty, 1.0 = wall-to-wall during waking hours)
            per_day: list of dicts (for week/month ranges):
                     [{date_label, weekday, event_count, hours_booked}]
            range_label: echoed back
    """
    from datetime import datetime, timedelta
    from collections import defaultdict

    facts: Dict[str, Any] = {
        'range_label': range_label,
        'total_events': len(events),
        'timed_events': 0,
        'all_day_events': 0,
        'total_minutes_booked': 0,
        'total_hours_booked': 0.0,
        'longest_meeting': None,
        'shortest_meeting': None,
        'longest_free_window': None,
        'free_windows_60min_or_more': [],
        'back_to_back_streaks': [],
        'density_score': 0.0,
        'per_day': []
    }

    if not events:
        return facts

    # Parse and categorize events
    timed = []  # list of (start_dt, end_dt, summary, duration_min)
    all_day_count = 0
    longest_min = 0
    longest_event = None
    shortest_min = float('inf')
    shortest_event = None

    for ev in events:
        if ev.get('is_all_day'):
            all_day_count += 1
            continue
        if ev.get('status') == 'cancelled':
            continue
        try:
            start_dt = datetime.fromisoformat(ev['start'].replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(ev['end'].replace('Z', '+00:00'))
        except Exception:
            continue
        duration_min = int((end_dt - start_dt).total_seconds() / 60)
        if duration_min <= 0:
            continue
        summary = ev.get('summary', '(no title)')
        timed.append((start_dt, end_dt, summary, duration_min))
        if duration_min > longest_min:
            longest_min = duration_min
            longest_event = {
                'summary': summary,
                'duration_minutes': duration_min,
                'start': ev['start']
            }
        if duration_min < shortest_min:
            shortest_min = duration_min
            shortest_event = {
                'summary': summary,
                'duration_minutes': duration_min,
                'start': ev['start']
            }

    facts['timed_events'] = len(timed)
    facts['all_day_events'] = all_day_count
    facts['total_minutes_booked'] = sum(t[3] for t in timed)
    facts['total_hours_booked'] = round(facts['total_minutes_booked'] / 60.0, 1)
    facts['longest_meeting'] = longest_event
    facts['shortest_meeting'] = shortest_event if shortest_event and shortest_min != float('inf') else None

    # Sort timed events by start
    timed.sort(key=lambda t: t[0])

    # Detect back-to-back streaks (3+ consecutive meetings with <15min gaps)
    if len(timed) >= 3:
        streak_start_idx = 0
        for i in range(1, len(timed)):
            gap_min = (timed[i][0] - timed[i - 1][1]).total_seconds() / 60
            if gap_min >= 15:
                # Streak broken
                if i - streak_start_idx >= 3:
                    facts['back_to_back_streaks'].append({
                        'count': i - streak_start_idx,
                        'start': timed[streak_start_idx][0].isoformat(),
                        'end': timed[i - 1][1].isoformat(),
                        'start_label': _format_iso_for_display(timed[streak_start_idx][0].isoformat()),
                        'end_label': _format_iso_for_display(timed[i - 1][1].isoformat())
                    })
                streak_start_idx = i
        # Tail streak
        if len(timed) - streak_start_idx >= 3:
            facts['back_to_back_streaks'].append({
                'count': len(timed) - streak_start_idx,
                'start': timed[streak_start_idx][0].isoformat(),
                'end': timed[-1][1].isoformat(),
                'start_label': _format_iso_for_display(timed[streak_start_idx][0].isoformat()),
                'end_label': _format_iso_for_display(timed[-1][1].isoformat())
            })

    # Detect free windows >= 60 min between consecutive events (within waking hours,
    # 8 AM to 9 PM local — used for deep-work suggestions)
    free_windows = []
    longest_free_min = 0
    longest_free_window = None

    if timed:
        # Iterate gaps between consecutive timed events
        for i in range(1, len(timed)):
            gap_start = timed[i - 1][1]
            gap_end = timed[i][0]
            gap_min = (gap_end - gap_start).total_seconds() / 60
            if gap_min >= 60:
                # Restrict to waking hours by clipping
                clipped_start = gap_start
                clipped_end = gap_end
                if clipped_start.hour < 8:
                    clipped_start = clipped_start.replace(hour=8, minute=0, second=0, microsecond=0)
                if clipped_end.hour >= 21:
                    clipped_end = clipped_end.replace(hour=21, minute=0, second=0, microsecond=0)
                clipped_min = (clipped_end - clipped_start).total_seconds() / 60
                if clipped_min >= 60:
                    window = {
                        'start': clipped_start.isoformat(),
                        'end': clipped_end.isoformat(),
                        'duration_minutes': int(clipped_min),
                        'display': f"{_format_iso_for_display(clipped_start.isoformat())} – {clipped_end.strftime('%I:%M %p').lstrip('0')}"
                    }
                    free_windows.append(window)
                    if clipped_min > longest_free_min:
                        longest_free_min = clipped_min
                        longest_free_window = window

    facts['free_windows_60min_or_more'] = sorted(
        free_windows,
        key=lambda w: w['duration_minutes'],
        reverse=True
    )[:5]
    facts['longest_free_window'] = longest_free_window

    # Per-day breakdown (for week/month ranges)
    if range_label in ('week', 'month'):
        per_day_map = defaultdict(lambda: {'count': 0, 'minutes': 0})
        for start_dt, end_dt, summary, duration_min in timed:
            day_key = start_dt.date().isoformat()
            per_day_map[day_key]['count'] += 1
            per_day_map[day_key]['minutes'] += duration_min
        per_day_list = []
        for day_key in sorted(per_day_map.keys()):
            d = datetime.fromisoformat(day_key)
            per_day_list.append({
                'date': day_key,
                'date_label': d.strftime('%a, %b %d'),
                'weekday': d.strftime('%A'),
                'event_count': per_day_map[day_key]['count'],
                'hours_booked': round(per_day_map[day_key]['minutes'] / 60.0, 1)
            })
        facts['per_day'] = per_day_list

    # Density score: hours_booked / 13 (waking hours), clamped to [0, 1]
    # For multi-day ranges, normalize per day
    if range_label == 'today' or range_label == 'tomorrow':
        days_in_range = 1
    elif range_label == 'week':
        days_in_range = 7
    elif range_label == 'month':
        days_in_range = 30
    else:
        days_in_range = max(1, len(facts['per_day']) or 1)

    waking_hours_total = days_in_range * 13.0
    density = facts['total_hours_booked'] / waking_hours_total if waking_hours_total > 0 else 0.0
    facts['density_score'] = round(min(1.0, max(0.0, density)), 2)

    return facts


async def analyze_calendar(token_data: Dict[str, Any],
                            question: str,
                            range_label: str = "week",
                            time_min: Optional[str] = None,
                            time_max: Optional[str] = None,
                            timezone_str: str = "Asia/Kolkata") -> Dict[str, Any]:
    """
    The full reasoning pipeline:
    1. Fetch events for the range
    2. Compute structural facts
    3. Send to Groq with the calendar-advisor system prompt
    4. Return prose response + facts (so frontend can show structured stats too)

    Args:
        token_data: OAuth tokens
        question: User's natural-language question
        range_label: "today" | "tomorrow" | "week" | "month" (default "week")
        time_min, time_max: optional explicit ISO range — overrides range_label
        timezone_str: User's timezone (default Asia/Kolkata)

    Returns:
        {
            "response": str,        # AI advisor prose
            "facts": dict,          # structural facts (from compute_calendar_facts)
            "events_count": int,
            "range": str
        }
    """
    from datetime import datetime, timedelta, timezone as tz
    import json
    import os as _os

    # Resolve time range from range_label if not given explicitly
    if not (time_min and time_max):
        now = datetime.now(tz.utc)
        if range_label == "today":
            time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            time_max = now.replace(hour=23, minute=59, second=59).isoformat()
        elif range_label == "tomorrow":
            tomorrow = now + timedelta(days=1)
            time_min = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            time_max = tomorrow.replace(hour=23, minute=59, second=59).isoformat()
        elif range_label == "month":
            time_min = now.isoformat()
            time_max = (now + timedelta(days=30)).isoformat()
        else:
            # Default: week
            range_label = "week"
            time_min = now.isoformat()
            time_max = (now + timedelta(days=7)).isoformat()

    # Fetch events
    try:
        events = fetch_events(
            token_data,
            time_min=time_min,
            time_max=time_max,
            max_results=50
        )
    except Exception as e:
        logger.error(f"analyze_calendar — fetch failed: {e}")
        raise

    # Compute structural facts
    facts = compute_calendar_facts(events, range_label=range_label, timezone_str=timezone_str)

    # Build a compact event list for the LLM (don't dump full Google JSON — too noisy)
    compact_events = []
    for ev in events[:30]:  # cap at 30 to control prompt size
        compact_events.append({
            'summary': ev.get('summary', '(no title)'),
            'start': ev.get('start', ''),
            'end': ev.get('end', ''),
            'is_all_day': ev.get('is_all_day', False)
        })

    # Build the user payload sent to the LLM
    user_payload = {
        'question': question,
        'range': range_label,
        'timezone': timezone_str,
        'today': datetime.now(tz.utc).strftime('%A, %b %d %Y'),
        'computed_facts': facts,
        'events': compact_events
    }

    # Call Groq
    try:
        from groq import Groq

        client = Groq(api_key=_os.getenv("GROQ_API_KEY"))

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": ADVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, indent=2, default=str)}
            ],
            temperature=0.4,   # slightly creative but grounded
            max_tokens=400     # advisor responses are concise by design
        )

        prose = completion.choices[0].message.content.strip()

        logger.info(
            f"Calendar analyze: range={range_label}, events={len(events)}, "
            f"density={facts['density_score']}, response_len={len(prose)}"
        )

        return {
            "response": prose,
            "facts": facts,
            "events_count": len(events),
            "range": range_label
        }

    except Exception as e:
        logger.error(f"analyze_calendar — Groq call failed: {e}")
        # Fall back to a deterministic summary so we don't 500 to the user
        fallback = _build_fallback_summary(facts, range_label)
        return {
            "response": fallback,
            "facts": facts,
            "events_count": len(events),
            "range": range_label,
            "_error": str(e)
        }


def _build_fallback_summary(facts: Dict[str, Any], range_label: str) -> str:
    """
    Deterministic non-LLM summary used only when Groq is unreachable.
    Better than a 500 error — the user still gets useful info.
    """
    if facts['total_events'] == 0:
        return f"Your calendar is empty for the {range_label}. You're free!"

    parts = []
    if facts['timed_events'] > 0:
        parts.append(
            f"You have {facts['timed_events']} timed event"
            f"{'s' if facts['timed_events'] != 1 else ''} "
            f"({facts['total_hours_booked']} hours total)"
        )
    if facts['all_day_events'] > 0:
        parts.append(
            f"{facts['all_day_events']} all-day event"
            f"{'s' if facts['all_day_events'] != 1 else ''}"
        )

    summary = "Here's the snapshot for your " + range_label + ": " + ", ".join(parts) + "."

    if facts['back_to_back_streaks']:
        s = facts['back_to_back_streaks'][0]
        summary += f" There's a back-to-back streak of {s['count']} meetings starting {s['start_label']}."
    if facts['longest_free_window']:
        w = facts['longest_free_window']
        summary += f" Your longest free window is {w['duration_minutes']} min around {_format_iso_for_display(w['start'])}."

    return summary