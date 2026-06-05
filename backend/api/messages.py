"""
OmniAI - Message Edit & Delete API
Step 52: Edit user messages, delete messages, delete-and-after for retry

Every endpoint is scoped to the authenticated user: a message can only be
edited or deleted if it belongs to a conversation owned by the caller.
This prevents one account from touching another account's messages (IDOR).
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

from database import get_db

router = APIRouter(prefix="/api/v1", tags=["messages"])


class EditMessageRequest(BaseModel):
    content: str


# ============================================================================
# AUTH / OWNERSHIP HELPERS
# ============================================================================

async def _require_user_id(request: Request, db: AsyncSession) -> str:
    """Extract the authenticated user_id from the JWT, or raise 401."""
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


async def _get_owned_message(db: AsyncSession, message_id: str, user_id: str):
    """
    Return (id, role, conversation_id, created_at) for the message ONLY if it
    belongs to a conversation owned by user_id. Returns None otherwise.
    """
    result = await db.execute(
        text("""
            SELECT m.id, m.role, m.conversation_id, m.created_at
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.id = :id AND c.user_id = :user_id
        """),
        {"id": message_id, "user_id": user_id}
    )
    return result.fetchone()


# ============================================================================
# EDIT A USER MESSAGE
# ============================================================================

@router.put("/messages/{message_id}")
async def edit_message(
    message_id: str,
    body: EditMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Edit a user message (only within your own conversations)"""

    user_id = await _require_user_id(request, db)

    msg = await _get_owned_message(db, message_id, user_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg[1] != "user":
        raise HTTPException(status_code=400, detail="Can only edit user messages")

    await db.execute(
        text("""
            UPDATE messages
            SET content = :content, updated_at = NOW()
            WHERE id = :id
        """),
        {"content": body.content, "id": message_id}
    )
    await db.commit()

    return {
        "status": "updated",
        "message_id": message_id,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# DELETE A SINGLE MESSAGE
# ============================================================================

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Delete a single message (only within your own conversations)"""

    user_id = await _require_user_id(request, db)

    msg = await _get_owned_message(db, message_id, user_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    await db.execute(
        text("DELETE FROM messages WHERE id = :id"),
        {"id": message_id}
    )
    await db.commit()

    return {
        "status": "deleted",
        "message_id": message_id,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# DELETE MESSAGE AND EVERYTHING AFTER (for edit & retry)
# ============================================================================

@router.delete("/messages/{message_id}/and-after")
async def delete_message_and_after(
    message_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a message and all messages after it in the conversation.
    Used for 'edit & retry'. Scoped to the caller's own conversations.
    """

    user_id = await _require_user_id(request, db)

    msg = await _get_owned_message(db, message_id, user_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    conv_id = str(msg[2])
    created_at = msg[3]

    delete_result = await db.execute(
        text("""
            DELETE FROM messages
            WHERE conversation_id = :conv_id
            AND created_at >= :created_at
        """),
        {"conv_id": conv_id, "created_at": created_at}
    )
    await db.commit()

    return {
        "status": "deleted",
        "conversation_id": conv_id,
        "deleted_count": delete_result.rowcount,
        "timestamp": datetime.utcnow().isoformat()
    }