"""
OmniAI - Export Conversations API
Step 51: Export conversations as TXT, MD, JSON
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
import json

from database import get_db

router = APIRouter(prefix="/api/v1", tags=["export"])


# ============================================================================
# HELPER: Fetch conversation + messages from DB
# ============================================================================

async def get_conversation_data(conversation_id: str, db: AsyncSession) -> dict:
    """Fetch conversation with all messages"""
    
    conv_result = await db.execute(
        text("SELECT id, title, created_at, updated_at FROM conversations WHERE id = :id"),
        {"id": conversation_id}
    )
    conv = conv_result.fetchone()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    msg_result = await db.execute(
        text("""
            SELECT role, content, created_at 
            FROM messages 
            WHERE conversation_id = :conv_id 
            ORDER BY created_at ASC
        """),
        {"conv_id": conversation_id}
    )
    messages = msg_result.fetchall()
    
    return {
        "id": str(conv[0]),
        "title": conv[1] or "Untitled Conversation",
        "created_at": conv[2].isoformat() if conv[2] else None,
        "updated_at": conv[3].isoformat() if conv[3] else None,
        "messages": [
            {
                "role": row[0],
                "content": row[1],
                "timestamp": row[2].isoformat() if row[2] else None
            }
            for row in messages
        ]
    }


# ============================================================================
# FORMAT: PLAIN TEXT
# ============================================================================

def format_as_txt(data: dict) -> str:
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  {data['title']}")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Exported from OmniAI")
    lines.append(f"  Created: {data['created_at']}")
    lines.append(f"  Messages: {len(data['messages'])}")
    lines.append(f"{'=' * 60}")
    lines.append("")
    
    for msg in data["messages"]:
        sender = "You" if msg["role"] == "user" else "OmniAI"
        timestamp = msg["timestamp"] or ""
        lines.append(f"[{sender}] ({timestamp})")
        lines.append(msg["content"])
        lines.append("")
        lines.append("-" * 40)
        lines.append("")
    
    return "\n".join(lines)


# ============================================================================
# FORMAT: MARKDOWN
# ============================================================================

def format_as_md(data: dict) -> str:
    lines = []
    lines.append(f"# {data['title']}")
    lines.append("")
    lines.append(f"> Exported from OmniAI on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"> Created: {data['created_at']}")
    lines.append(f"> Messages: {len(data['messages'])}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    for msg in data["messages"]:
        if msg["role"] == "user":
            lines.append(f"### 👤 You")
        else:
            lines.append(f"### 🤖 OmniAI")
        
        if msg["timestamp"]:
            lines.append(f"*{msg['timestamp']}*")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


# ============================================================================
# FORMAT: JSON
# ============================================================================

def format_as_json(data: dict) -> str:
    export_data = {
        "export_info": {
            "source": "OmniAI",
            "exported_at": datetime.utcnow().isoformat(),
            "format_version": "1.0"
        },
        "conversation": {
            "id": data["id"],
            "title": data["title"],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "message_count": len(data["messages"])
        },
        "messages": data["messages"]
    }
    return json.dumps(export_data, indent=2, ensure_ascii=False)


# ============================================================================
# EXPORT SINGLE CONVERSATION
# ============================================================================

@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = "md",
    db: AsyncSession = Depends(get_db)
):
    """
    Export a conversation in the specified format.
    
    Params:
        conversation_id: UUID of the conversation
        format: 'txt', 'md', or 'json' (default: 'md')
    """
    
    format = format.lower()
    if format not in ("txt", "md", "json"):
        raise HTTPException(status_code=400, detail="Invalid format. Use 'txt', 'md', or 'json'")
    
    data = await get_conversation_data(conversation_id, db)
    
    if format == "txt":
        content = format_as_txt(data)
        media_type = "text/plain"
    elif format == "md":
        content = format_as_md(data)
        media_type = "text/markdown"
    else:
        content = format_as_json(data)
        media_type = "application/json"
    
    safe_title = "".join(c for c in data["title"] if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title[:50] or "conversation"
    filename = f"{safe_title}.{format}"
    
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ============================================================================
# EXPORT ALL CONVERSATIONS (BACKUP)
# ============================================================================

@router.get("/conversations/export/all")
async def export_all_conversations(
    format: str = "json",
    db: AsyncSession = Depends(get_db)
):
    """Export all conversations as a single JSON backup file."""
    
    result = await db.execute(
        text("SELECT id FROM conversations ORDER BY created_at DESC")
    )
    conv_ids = [str(row[0]) for row in result.fetchall()]
    
    if not conv_ids:
        raise HTTPException(status_code=404, detail="No conversations found")
    
    all_conversations = []
    for conv_id in conv_ids:
        try:
            data = await get_conversation_data(conv_id, db)
            all_conversations.append(data)
        except HTTPException:
            continue
    
    export_data = {
        "export_info": {
            "source": "OmniAI",
            "exported_at": datetime.utcnow().isoformat(),
            "format_version": "1.0",
            "total_conversations": len(all_conversations),
            "total_messages": sum(len(c["messages"]) for c in all_conversations)
        },
        "conversations": all_conversations
    }
    
    content = json.dumps(export_data, indent=2, ensure_ascii=False)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="omniai_backup_{timestamp}.json"'}
    )


# ============================================================================
# FULL-TEXT SEARCH (Step 54)
# ============================================================================

@router.get("/search")
async def search_conversations(
    q: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Full-text search across all messages"""
    
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query too short")
    
    result = await db.execute(
        text("""
            SELECT 
                m.id,
                m.conversation_id,
                m.content,
                m.role,
                m.created_at,
                c.title as conversation_title,
                ts_rank(m.search_vector, plainto_tsquery('english', :query)) as rank
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.search_vector @@ plainto_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """),
        {"query": q, "limit": limit}
    )
    
    matches = []
    for row in result.fetchall():
        matches.append({
            "message_id": str(row[0]),
            "conversation_id": str(row[1]),
            "content_preview": row[2][:200] + "..." if len(row[2]) > 200 else row[2],
            "role": row[3],
            "timestamp": row[4].isoformat() if row[4] else None,
            "conversation_title": row[5],
            "relevance": float(row[6])
        })
    
    return {
        "query": q,
        "results": matches,
        "total": len(matches)
    }