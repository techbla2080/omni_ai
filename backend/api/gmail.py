"""
OmniAI Gmail API Router
Handles Gmail OAuth and email operations
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from services.gmail_service import (
    get_auth_url,
    exchange_code_for_tokens,
    fetch_emails,
    send_email,
    search_emails,
    get_user_email,
    get_unread_count,
    mark_as_read
)
from database.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gmail", tags=["gmail"])


# ============================================================
# Request/Response Models
# ============================================================

class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    reply_to_id: Optional[str] = None


class GmailQueryRequest(BaseModel):
    query: str
    max_results: int = 10


# ============================================================
# Helper — get current user ID from request
# ============================================================

async def get_user_id(request: Request, db: AsyncSession) -> str:
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    return user_id


# ============================================================
# Helper — get stored Gmail tokens for current user
# ============================================================

async def get_gmail_tokens(user_id: str, db: AsyncSession) -> dict:
    result = await db.execute(
        text("SELECT gmail_tokens FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    row = result.fetchone()
    if not row or not row[0]:
        raise HTTPException(
            status_code=400,
            detail="Gmail not connected. Please connect your Gmail account first."
        )
    tokens = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return tokens


# ============================================================
# OAuth Endpoints
# ============================================================

@router.get("/connect")
async def connect_gmail(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Start Gmail OAuth flow — pass JWT as state so callback can save tokens"""
    try:
        user_id = await get_user_id(request, db)

        # Get the JWT token from the Authorization header to use as state
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if not token:
            # Try cookie
            token = request.cookies.get("access_token", "")

        # Pass token as state parameter
        from services.gmail_service import get_oauth_flow
        flow = get_oauth_flow()
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=token  # JWT token as state
        )
        return {"auth_url": auth_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def gmail_callback(
    code: str = Query(...),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth callback — exchange code for tokens and save them"""
    if error:
        return RedirectResponse(url=f"/?gmail_error={error}")

    try:
        # Exchange code for tokens
        tokens = exchange_code_for_tokens(code)
        gmail_email = get_user_email(tokens)
        logger.info(f"Gmail connected for: {gmail_email}")

        # Use state (JWT token) to identify user and save tokens
        if state:
            try:
                from jose import jwt
                from utils.config import settings

                payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
                user_id = payload.get("sub")

                if user_id:
                    tokens_json = json.dumps(tokens)
                    await db.execute(
                        text("UPDATE users SET gmail_tokens = :tokens, gmail_email = :email WHERE id = :user_id"),
                        {"tokens": tokens_json, "email": gmail_email, "user_id": user_id}
                    )
                    await db.commit()
                    logger.info(f"Tokens saved for user {user_id}")

            except Exception as e:
                logger.error(f"Error saving tokens from state: {e}")

        return RedirectResponse(
            url=f"/?gmail_connected=true&gmail_email={gmail_email}"
        )

    except Exception as e:
        logger.error(f"Gmail callback error: {e}")
        return RedirectResponse(url=f"/?gmail_error=callback_failed")


@router.post("/save-tokens")
async def save_gmail_tokens(
    tokens: dict,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Save Gmail tokens to user record in database"""
    try:
        user_id = await get_user_id(request, db)
        tokens_json = json.dumps(tokens)
        gmail_email = get_user_email(tokens)
        await db.execute(
            text("UPDATE users SET gmail_tokens = :tokens, gmail_email = :email WHERE id = :user_id"),
            {"tokens": tokens_json, "email": gmail_email, "user_id": user_id}
        )
        await db.commit()
        return {"success": True, "message": "Gmail connected successfully", "email": gmail_email}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def gmail_status(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Check if Gmail is connected for current user"""
    try:
        user_id = await get_user_id(request, db)
        result = await db.execute(
            text("SELECT gmail_tokens, gmail_email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        row = result.fetchone()
        if row and row[0]:
            return {"connected": True, "email": row[1] or "Connected"}
        return {"connected": False}
    except HTTPException:
        return {"connected": False}
    except Exception as e:
        logger.error(f"Error checking Gmail status: {e}")
        return {"connected": False}


@router.delete("/disconnect")
async def disconnect_gmail(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Disconnect Gmail from user account"""
    try:
        user_id = await get_user_id(request, db)
        await db.execute(
            text("UPDATE users SET gmail_tokens = NULL, gmail_email = NULL WHERE id = :user_id"),
            {"user_id": user_id}
        )
        await db.commit()
        return {"success": True, "message": "Gmail disconnected"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Email Reading Endpoints
# ============================================================

@router.get("/inbox")
async def get_inbox(
    request: Request,
    max_results: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_user_id(request, db)
    tokens = await get_gmail_tokens(user_id, db)
    try:
        emails = fetch_emails(tokens, query='in:inbox', max_results=max_results)
        return {"emails": emails, "count": len(emails)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unread")
async def get_unread(
    request: Request,
    max_results: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_user_id(request, db)
    tokens = await get_gmail_tokens(user_id, db)
    try:
        emails = fetch_emails(tokens, query='is:unread in:inbox', max_results=max_results)
        count = get_unread_count(tokens)
        return {"emails": emails, "unread_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_gmail(
    request: Request,
    q: str = Query(...),
    max_results: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_user_id(request, db)
    tokens = await get_gmail_tokens(user_id, db)
    try:
        emails = search_emails(tokens, query=q, max_results=max_results)
        return {"emails": emails, "query": q, "count": len(emails)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read/{message_id}")
async def mark_email_read(
    message_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_user_id(request, db)
    tokens = await get_gmail_tokens(user_id, db)
    success = mark_as_read(tokens, message_id)
    return {"success": success}


# ============================================================
# Email Sending Endpoint
# ============================================================

@router.post("/send")
async def send_gmail(
    request: Request,
    body: SendEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_user_id(request, db)
    tokens = await get_gmail_tokens(user_id, db)
    try:
        result = send_email(
            tokens,
            to=body.to,
            subject=body.subject,
            body=body.body,
            reply_to_id=body.reply_to_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# AI-Powered Email Endpoint
# ============================================================

@router.post("/ask")
async def ask_about_email(
    request: Request,
    body: GmailQueryRequest,
    db: AsyncSession = Depends(get_db)
):
    from services.llm import llm_service

    user_id = await get_user_id(request, db)
    tokens = await get_gmail_tokens(user_id, db)

    try:
        query = 'in:inbox'
        user_q = body.query.lower()

        if 'unread' in user_q:
            query = 'is:unread in:inbox'
        elif 'today' in user_q:
            query = 'in:inbox newer_than:1d'
        elif 'week' in user_q:
            query = 'in:inbox newer_than:7d'
        elif 'sent' in user_q:
            query = 'in:sent'

        emails = fetch_emails(tokens, query=query, max_results=5)

        if not emails:
            return {"response": "No emails found matching your query.", "emails_analyzed": 0}

        email_context = ""
        for i, email in enumerate(emails, 1):
            email_context += f"""
Email {i}:
From: {email['from']}
Subject: {email['subject']}
Date: {email['date']}
Preview: {email['snippet']}
Body: {email['body'][:500]}
---
"""

        system_prompt = """You are OmniAI, an AI assistant with access to the user's Gmail.
Answer the user's question based on the email data provided. Be concise and helpful."""

        prompt = f"""Here are the user's recent emails:

{email_context}

User's question: {body.query}

Please answer based on the emails above."""

        response = await llm_service.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1024
        )

        return {"response": response, "emails_analyzed": len(emails)}

    except Exception as e:
        logger.error(f"Gmail ask error: {e}")
        raise HTTPException(status_code=500, detail=str(e))