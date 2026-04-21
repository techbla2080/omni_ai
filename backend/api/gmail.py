"""
OmniAI Gmail API Router
Handles Gmail OAuth and email operations
"""

import json
import logging
import re
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
# #28 — AI-Powered Email Reasoning (upgraded)
# ============================================================

def infer_email_query(user_q: str) -> dict:
    """
    Parse the user's natural language question into a Gmail search query + intent label.
    Returns: {"gmail_query": str, "intent": str, "max_results": int}
    """
    q = user_q.lower()
    gmail_query = "in:inbox"
    intent = "general"
    max_results = 15

    # --- SENT folder intents (replies tracking) ---
    if any(k in q for k in ["haven't replied", "havent replied", "not replied", "unreplied", "need to reply"]):
        # Fetch inbox — we'll reason about which ones user hasn't replied to
        gmail_query = "in:inbox newer_than:14d"
        intent = "unreplied"
        max_results = 20

    # --- URGENT / IMPORTANT ---
    elif any(k in q for k in ["urgent", "important", "priority", "critical"]):
        gmail_query = "(is:unread OR is:important) in:inbox newer_than:7d"
        intent = "urgent"
        max_results = 15

    # --- ACTION ITEMS / PENDING ---
    elif any(k in q for k in ["action item", "pending", "todo", "to do", "follow up", "follow-up"]):
        gmail_query = "in:inbox newer_than:14d"
        intent = "action_items"
        max_results = 20

    # --- SUMMARIZE ---
    elif any(k in q for k in ["summarize", "summary", "recap", "overview", "digest"]):
        if "today" in q:
            gmail_query = "in:inbox newer_than:1d"
        elif "week" in q:
            gmail_query = "in:inbox newer_than:7d"
        elif "month" in q:
            gmail_query = "in:inbox newer_than:30d"
        else:
            gmail_query = "in:inbox newer_than:7d"
        intent = "summarize"
        max_results = 20

    # --- DATE RANGE ---
    elif "today" in q:
        gmail_query = "in:inbox newer_than:1d"
        intent = "date_range"
    elif "yesterday" in q:
        gmail_query = "in:inbox newer_than:2d older_than:1d"
        intent = "date_range"
    elif "this week" in q or "week" in q:
        gmail_query = "in:inbox newer_than:7d"
        intent = "date_range"
    elif "this month" in q or "month" in q:
        gmail_query = "in:inbox newer_than:30d"
        intent = "date_range"

    # --- UNREAD ---
    elif "unread" in q:
        gmail_query = "is:unread in:inbox"
        intent = "unread"

    # --- SENT ---
    elif "sent" in q and "resent" not in q:
        gmail_query = "in:sent newer_than:7d"
        intent = "sent"

    # --- SENDER FILTER: "from <name>" ---
    # Try to detect "from X" pattern and add to the query
    sender_match = re.search(r"\bfrom\s+([a-z0-9._@\-]+)", q)
    if sender_match:
        sender = sender_match.group(1).strip().rstrip(".,!?")
        if sender and sender not in {"my", "me", "the", "an", "a"}:
            gmail_query = f"{gmail_query} from:{sender}"
            if intent == "general":
                intent = "sender_filter"

    # --- TOPIC FILTER: "about X" ---
    about_match = re.search(r"\babout\s+([a-z0-9 \-]+?)(?:\s+(?:today|yesterday|this|last|from|$)|$)", q)
    if about_match:
        topic = about_match.group(1).strip()
        if topic and len(topic) > 2:
            gmail_query = f'{gmail_query} ({topic})'
            if intent == "general":
                intent = "topic_filter"

    return {
        "gmail_query": gmail_query,
        "intent": intent,
        "max_results": max_results
    }


def build_ask_system_prompt(intent: str) -> str:
    """Build a specialized system prompt based on the detected intent."""
    base = """You are OmniAI, an intelligent email assistant with access to the user's Gmail inbox.

You will be given a list of the user's emails (sender, subject, date, snippet, body).
Your job is to answer the user's question by reasoning across these emails.

GUIDELINES:
- Be concrete: mention senders by name, reference subject lines, cite dates.
- Be concise: use short bullet points or numbered lists. Avoid fluff.
- Be honest: if the information isn't in the emails, say so.
- Respect privacy: don't fabricate details not present in the emails.
- Use markdown formatting (bold for names, bullets for lists) to make answers scannable."""

    if intent == "summarize":
        return base + """

TASK: Summarize the inbox.
- Start with a one-line overview (total emails, key themes).
- Group emails into categories (urgent, FYI, newsletters, personal, promotional).
- Call out the top 3-5 most important items with sender name and what they want.
- End with any clear action items you notice."""

    if intent == "urgent":
        return base + """

TASK: Identify what's urgent.
- List items that genuinely need the user's attention soon.
- For each, say WHO it's from, WHAT they need, and WHY it's urgent (deadline, follow-up, escalation).
- If nothing is truly urgent, say so plainly — don't invent urgency."""

    if intent == "action_items":
        return base + """

TASK: Extract pending action items.
- Focus on emails where someone is asking the user to DO something.
- Format as a numbered list: "[Sender]: [what they need] [deadline if any]".
- Skip newsletters, promotional emails, FYI-only messages.
- If there are no clear action items, say "Nothing actionable in this batch."."""

    if intent == "unreplied":
        return base + """

TASK: Identify emails the user likely hasn't replied to yet.
- Look for emails where the sender is asking a question or expecting a response.
- Pay attention to who's writing and when.
- Format as: "[Sender] ([date]): [what they're asking]".
- Note: you don't have access to the Sent folder, so make your best guess based on inbox signals (questions, requests, follow-ups)."""

    return base + """

TASK: Answer the user's question directly based on the emails."""


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
        # #28 — Intelligent query routing
        routing = infer_email_query(body.query)
        gmail_query = routing["gmail_query"]
        intent = routing["intent"]
        max_results = routing["max_results"]

        logger.info(f"[ask] user_q='{body.query}' intent={intent} gmail_query='{gmail_query}'")

        emails = fetch_emails(tokens, query=gmail_query, max_results=max_results)

        if not emails:
            return {
                "response": "No emails found matching your question. Try broadening your request — e.g. 'summarize my inbox' or 'show unread emails'.",
                "emails_analyzed": 0,
                "emails": [],
                "intent": intent
            }

        # Build rich email context (more emails, longer bodies)
        email_context = ""
        for i, email in enumerate(emails, 1):
            body_preview = (email.get('body') or email.get('snippet') or '')[:1500]
            email_context += f"""
Email {i}:
From: {email.get('from', '')}
Subject: {email.get('subject', '')}
Date: {email.get('date', '')}
Unread: {email.get('is_unread', False)}
Body:
{body_preview}
---
"""

        system_prompt = build_ask_system_prompt(intent)

        prompt = f"""Here are the user's emails ({len(emails)} total):

{email_context}

User's question: "{body.query}"

Please answer based on the emails above. Follow the task guidelines in your instructions."""

        response = await llm_service.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1500
        )

        return {
            "response": response,
            "emails_analyzed": len(emails),
            "emails": emails,
            "intent": intent,
            "gmail_query": gmail_query
        }

    except Exception as e:
        logger.error(f"Gmail ask error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))