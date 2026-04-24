"""
OmniAI Calendar Service
Handles OAuth2 flow and Google Calendar API calls
"""

import os
import logging
from typing import Dict, Any

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
    
    Args:
        token_data: Saved OAuth tokens for the user
        time_min: ISO 8601 start time (e.g., '2026-04-21T00:00:00Z'). Defaults to now.
        time_max: ISO 8601 end time. Defaults to 7 days from now.
        max_results: Maximum number of events to return (1-50)
    
    Returns:
        List of event dicts with id, summary, start, end, location, attendees, etc.
    """
    from datetime import datetime, timedelta, timezone
    
    service = get_calendar_service(token_data)
    
    # Default time range: now → 7 days from now
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
        
        # Normalize event data for frontend consumption
        normalized = []
        for event in events:
            start = event.get('start', {})
            end = event.get('end', {})
            
            # Determine if it's an all-day event
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
            
            # Extract meet link if present
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

    Args:
        token_data: Saved OAuth tokens
        summary: Event title (e.g., "Team standup")
        start: ISO 8601 start time (e.g., "2026-04-25T15:00:00+05:30")
        end: ISO 8601 end time (e.g., "2026-04-25T16:00:00+05:30")
        description: Optional event description/notes
        location: Optional physical location or address
        attendees: Optional list of email strings (e.g., ["rahul@example.com"])
        add_meet: If True, generate a Google Meet link for the event
        timezone_str: IANA timezone (default: Asia/Kolkata for Indian users)

    Returns:
        Dict with created event details (id, summary, start, end, link, meet_link)
    """
    service = get_calendar_service(token_data)

    # Handle date-only vs datetime
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

    # Optional: add Google Meet conference
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

        # Extract meet link if generated
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