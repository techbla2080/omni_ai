"""
OmniAI - Message Edit & Delete API
Step 52: Edit user messages, delete messages, delete-and-after for retry
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

from database import get_db

router = APIRouter(prefix="/api/v1", tags=["messages"])


class EditMessageRequest(BaseModel):
    content: str


# ============================================================================
# EDIT A USER MESSAGE
# ============================================================================

@router.put("/messages/{message_id}")
async def edit_message(
    message_id: str,
    request: EditMessageRequest,
    db: AsyncSession = Depends(get_db)
):
    """Edit a user message"""
    
    result = await db.execute(
        text("SELECT id, role FROM messages WHERE id = :id"),
        {"id": message_id}
    )
    msg = result.fetchone()
    
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
        {"content": request.content, "id": message_id}
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
    db: AsyncSession = Depends(get_db)
):
    """Delete a single message"""
    
    result = await db.execute(
        text("SELECT id FROM messages WHERE id = :id"),
        {"id": message_id}
    )
    if not result.fetchone():
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
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a message and all messages after it in the conversation.
    Used for 'edit & retry' — delete from edited message onwards,
    then frontend re-sends the edited message for a fresh AI response.
    """
    
    result = await db.execute(
        text("""
            SELECT id, conversation_id, created_at 
            FROM messages WHERE id = :id
        """),
        {"id": message_id}
    )
    msg = result.fetchone()
    
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    conv_id = str(msg[1])
    created_at = msg[2]
    
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