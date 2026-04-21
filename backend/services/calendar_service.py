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