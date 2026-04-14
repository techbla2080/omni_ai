"""
OmniAI Gmail API Router
Handles Gmail OAuth and email operations
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
from api.auth import get_current_user
from database.connection import get_db

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
# Helper — get stored Gmail tokens for current user
# ============================================================

async def get_gmail_tokens(current_user: dict, db: AsyncSession) -> dict:
    """Get stored Gmail OAuth tokens for the current user"""
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT gmail_tokens FROM users WHERE id = :user_id"),
        {"user_id": current_user["id"]}
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
async def connect_gmail(current_user: dict = Depends(get_current_user)):
    """Start Gmail OAuth flow — redirect user to Google"""
    try:
        auth_url = get_auth_url()
        return {"auth_url": auth_url}
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
    """Handle Google OAuth callback — exchange code for tokens"""
    if error:
        return RedirectResponse(url=f"/?gmail_error={error}")

    try:
        # Exchange code for tokens
        tokens = exchange_code_for_tokens(code)

        # Get user's email from Google
        gmail_email = get_user_email(tokens)
        logger.info(f"Gmail connected for: {gmail_email}")

        # Store tokens in session/cookie temporarily
        # We'll use a simple redirect with a flag
        # In production, you'd store based on session state
        tokens_json = json.dumps(tokens)

        # Redirect back to app with success
        return RedirectResponse(
            url=f"/?gmail_connected=true&gmail_email={gmail_email}"
        )

    except Exception as e:
        logger.error(f"Gmail callback error: {e}")
        return RedirectResponse(url=f"/?gmail_error=callback_failed")


@router.post("/save-tokens")
async def save_gmail_tokens(
    tokens: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Save Gmail tokens to user record in database"""
    try:
        from sqlalchemy import text
        tokens_json = json.dumps(tokens)
        await db.execute(
            text("UPDATE users SET gmail_tokens = :tokens WHERE id = :user_id"),
            {"tokens": tokens_json, "user_id": current_user["id"]}
        )
        await db.commit()
        return {"success": True, "message": "Gmail connected successfully"}
    except Exception as e:
        logger.error(f"Error saving tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def gmail_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if Gmail is connected for current user"""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT gmail_tokens, gmail_email FROM users WHERE id = :user_id"),
            {"user_id": current_user["id"]}
        )
        row = result.fetchone()
        if row and row[0]:
            return {
                "connected": True,
                "email": row[1] or "Connected"
            }
        return {"connected": False}
    except Exception as e:
        logger.error(f"Error checking Gmail status: {e}")
        return {"connected": False}


@router.delete("/disconnect")
async def disconnect_gmail(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Disconnect Gmail from user account"""
    try:
        from sqlalchemy import text
        await db.execute(
            text("UPDATE users SET gmail_tokens = NULL, gmail_email = NULL WHERE id = :user_id"),
            {"user_id": current_user["id"]}
        )
        await db.commit()
        return {"success": True, "message": "Gmail disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Email Reading Endpoints
# ============================================================

@router.get("/inbox")
async def get_inbox(
    max_results: int = Query(10, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get inbox emails"""
    tokens = await get_gmail_tokens(current_user, db)
    try:
        emails = fetch_emails(tokens, query='in:inbox', max_results=max_results)
        return {"emails": emails, "count": len(emails)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unread")
async def get_unread(
    max_results: int = Query(10, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get unread emails"""
    tokens = await get_gmail_tokens(current_user, db)
    try:
        emails = fetch_emails(tokens, query='is:unread in:inbox', max_results=max_results)
        count = get_unread_count(tokens)
        return {"emails": emails, "unread_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_gmail(
    q: str = Query(...),
    max_results: int = Query(10, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search emails with Gmail query"""
    tokens = await get_gmail_tokens(current_user, db)
    try:
        emails = search_emails(tokens, query=q, max_results=max_results)
        return {"emails": emails, "query": q, "count": len(emails)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read/{message_id}")
async def mark_email_read(
    message_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark email as read"""
    tokens = await get_gmail_tokens(current_user, db)
    success = mark_as_read(tokens, message_id)
    return {"success": success}


# ============================================================
# Email Sending Endpoint
# ============================================================

@router.post("/send")
async def send_gmail(
    request: SendEmailRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send an email"""
    tokens = await get_gmail_tokens(current_user, db)
    try:
        result = send_email(
            tokens,
            to=request.to,
            subject=request.subject,
            body=request.body,
            reply_to_id=request.reply_to_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# AI-Powered Email Endpoint
# ============================================================

@router.post("/ask")
async def ask_about_email(
    request: GmailQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Ask AI a question about your emails"""
    from services.llm import llm_service

    tokens = await get_gmail_tokens(current_user, db)

    try:
        # Determine Gmail search query from user's question
        query = 'in:inbox'
        user_q = request.query.lower()

        if 'unread' in user_q:
            query = 'is:unread in:inbox'
        elif 'today' in user_q:
            query = 'in:inbox newer_than:1d'
        elif 'week' in user_q:
            query = 'in:inbox newer_than:7d'
        elif 'sent' in user_q:
            query = 'in:sent'

        # Fetch relevant emails
        emails = fetch_emails(tokens, query=query, max_results=5)

        if not emails:
            return {"response": "No emails found matching your query."}

        # Build context for AI
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
You have been given email data. Answer the user's question based on this email data.
Be concise, helpful, and accurate. Format your response clearly."""

        prompt = f"""Here are the user's recent emails:

{email_context}

User's question: {request.query}

Please answer based on the emails above."""

        response = await llm_service.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1024
        )

        return {
            "response": response,
            "emails_analyzed": len(emails)
        }

    except Exception as e:
        logger.error(f"Gmail ask error: {e}")
        raise HTTPException(status_code=500, detail=str(e))