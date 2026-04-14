"""
OmniAI Gmail Service
Handles OAuth2 flow and Gmail API calls
"""

import os
import json
import base64
import logging
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://omniai.biz/api/v1/gmail/callback")


def get_oauth_flow() -> Flow:
    """Create OAuth2 flow"""
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
    """Get the Google OAuth authorization URL"""
    flow = get_oauth_flow()
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access + refresh tokens"""
    flow = get_oauth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES
    }


def get_gmail_service(token_data: Dict[str, Any]):
    """Build Gmail API service from stored token data"""
    credentials = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id", CLIENT_ID),
        client_secret=token_data.get("client_secret", CLIENT_SECRET),
        scopes=token_data.get("scopes", SCOPES)
    )

    # Refresh if expired
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    service = build('gmail', 'v1', credentials=credentials)
    return service, credentials


def get_user_email(token_data: Dict[str, Any]) -> str:
    """Get the Gmail address of the authenticated user"""
    try:
        service, _ = get_gmail_service(token_data)
        profile = service.users().getProfile(userId='me').execute()
        return profile.get('emailAddress', '')
    except Exception as e:
        logger.error(f"Error getting user email: {e}")
        return ''


def fetch_emails(token_data: Dict[str, Any], query: str = '', max_results: int = 10) -> List[Dict]:
    """Fetch emails from Gmail"""
    try:
        service, _ = get_gmail_service(token_data)

        # Build query
        if not query:
            query = 'in:inbox'

        result = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = result.get('messages', [])
        emails = []

        for msg in messages:
            email_data = get_email_detail(service, msg['id'])
            if email_data:
                emails.append(email_data)

        return emails

    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        raise


def get_email_detail(service, message_id: str) -> Optional[Dict]:
    """Get detailed info for a single email"""
    try:
        msg = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = msg.get('payload', {}).get('headers', [])
        header_dict = {h['name'].lower(): h['value'] for h in headers}

        # Extract body
        body = extract_body(msg.get('payload', {}))

        # Extract labels
        labels = msg.get('labelIds', [])
        is_unread = 'UNREAD' in labels

        return {
            'id': message_id,
            'thread_id': msg.get('threadId', ''),
            'from': header_dict.get('from', ''),
            'to': header_dict.get('to', ''),
            'subject': header_dict.get('subject', '(no subject)'),
            'date': header_dict.get('date', ''),
            'snippet': msg.get('snippet', ''),
            'body': body[:2000] if body else '',  # limit body size
            'is_unread': is_unread,
            'labels': labels
        }

    except Exception as e:
        logger.error(f"Error getting email detail {message_id}: {e}")
        return None


def extract_body(payload: Dict) -> str:
    """Extract text body from email payload"""
    body = ''

    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
            elif part.get('mimeType') == 'text/html' and not body:
                data = part.get('body', {}).get('data', '')
                if data:
                    html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    # Basic HTML strip
                    import re
                    body = re.sub('<[^<]+?>', '', html)
    else:
        data = payload.get('body', {}).get('data', '')
        if data:
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

    return body.strip()


def send_email(token_data: Dict[str, Any], to: str, subject: str, body: str, reply_to_id: str = None) -> Dict:
    """Send an email via Gmail API"""
    try:
        service, _ = get_gmail_service(token_data)

        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        message.attach(MIMEText(body, 'plain'))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_body = {'raw': raw}

        # If replying to a thread
        if reply_to_id:
            original = service.users().messages().get(
                userId='me', id=reply_to_id, format='minimal'
            ).execute()
            send_body['threadId'] = original.get('threadId')

        result = service.users().messages().send(
            userId='me',
            body=send_body
        ).execute()

        return {
            'success': True,
            'message_id': result.get('id'),
            'thread_id': result.get('threadId')
        }

    except HttpError as e:
        logger.error(f"Gmail send error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise


def search_emails(token_data: Dict[str, Any], query: str, max_results: int = 10) -> List[Dict]:
    """Search emails with Gmail query syntax"""
    return fetch_emails(token_data, query=query, max_results=max_results)


def mark_as_read(token_data: Dict[str, Any], message_id: str) -> bool:
    """Mark email as read"""
    try:
        service, _ = get_gmail_service(token_data)
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error marking as read: {e}")
        return False


def get_unread_count(token_data: Dict[str, Any]) -> int:
    """Get count of unread emails"""
    try:
        service, _ = get_gmail_service(token_data)
        result = service.users().messages().list(
            userId='me',
            q='is:unread in:inbox',
            maxResults=1
        ).execute()
        return result.get('resultSizeEstimate', 0)
    except Exception as e:
        logger.error(f"Error getting unread count: {e}")
        return 0