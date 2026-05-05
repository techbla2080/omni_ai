"""
#38 — Memory management API endpoints.

User-facing CRUD over the user_memories table. All endpoints are auth-gated;
anonymous users have no memories to manage.

Endpoints:
  GET    /api/v1/memories                 — list active memories (optional history)
  PUT    /api/v1/memories/{memory_id}     — edit a memory's content
  DELETE /api/v1/memories/{memory_id}     — delete a single memory (soft)
  DELETE /api/v1/memories                 — delete ALL memories (GDPR "forget me")
  GET    /api/v1/memories/settings        — read memory preferences
  PUT    /api/v1/memories/settings        — update memory preferences (paused, etc.)

Pairs with services/memory.py (the implementation layer) and settings panel UI
in frontend/js/app.js (the user-facing surface).
"""

import json
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from services.memory import (
    get_all_user_memories,
    update_memory,
    delete_memory,
    delete_all_memories,
    count_active_memories,
    FREE_TIER_MEMORY_CAP,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


# ============================================================================
# Pydantic models
# ============================================================================

class MemoryItem(BaseModel):
    """A single memory as exposed to the frontend."""
    id: str
    content: str
    category: str
    confidence: float
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MemoriesListResponse(BaseModel):
    """Response shape for GET /memories."""
    memories: List[MemoryItem]
    total: int
    active_count: int
    cap: int  # the user's memory cap (free=10, pro=very high)
    is_pro: bool
    paused: bool  # whether memory_collection_paused is set


class UpdateMemoryRequest(BaseModel):
    """Body for PUT /memories/{memory_id}"""
    content: str = Field(..., max_length=600)


class MemorySettingsResponse(BaseModel):
    """Response shape for GET/PUT /memories/settings"""
    paused: bool
    is_pro: bool
    active_count: int
    cap: int


class UpdateSettingsRequest(BaseModel):
    """Body for PUT /memories/settings"""
    paused: Optional[bool] = None  # null = no change


# ============================================================================
# Auth helper
# ============================================================================

async def get_user_id(request: Request, db: AsyncSession) -> str:
    """
    Extract authenticated user_id from JWT.
    All memory endpoints require auth — anonymous users have no memories.
    """
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ============================================================================
# Preferences helpers — same pattern as settings.py / services/memory.py
# ============================================================================

async def _get_preferences(db: AsyncSession, user_id: str) -> dict:
    """Fetch user preferences JSONB safely. Returns {} if missing."""
    result = await db.execute(
        text("SELECT preferences FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    row = result.fetchone()
    if not row or row[0] is None:
        return {}
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


async def _save_preferences(db: AsyncSession, user_id: str, prefs: dict):
    """Persist the full preferences dict back to users table."""
    await db.execute(
        text("""
            UPDATE users
            SET preferences = CAST(:prefs AS JSONB),
                updated_at = NOW()
            WHERE id = :user_id
        """),
        {"prefs": json.dumps(prefs), "user_id": user_id}
    )
    await db.commit()


async def _is_pro_user(db: AsyncSession, user_id: str) -> bool:
    """Pro check via preferences flag (same as services/memory.py)."""
    prefs = await _get_preferences(db, user_id)
    return bool(prefs.get("memory_pro_unlocked", False))


async def _is_paused(db: AsyncSession, user_id: str) -> bool:
    prefs = await _get_preferences(db, user_id)
    return bool(prefs.get("memory_collection_paused", False))


def _build_settings_response(
    paused: bool,
    is_pro: bool,
    active_count: int
) -> MemorySettingsResponse:
    """Build the canonical settings response shape."""
    cap = 10000 if is_pro else FREE_TIER_MEMORY_CAP  # generous cap for Pro
    return MemorySettingsResponse(
        paused=paused,
        is_pro=is_pro,
        active_count=active_count,
        cap=cap
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=MemoriesListResponse)
async def list_memories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    include_superseded: bool = False
):
    """
    List the user's memories.
    
    Query params:
        include_superseded: if true, also return superseded (replaced) 
                            memories for an audit-style history view.
                            Default false — most UIs only show active.
    
    Returns active count, cap, and pause state alongside the list so the
    frontend can render the cap counter ("3/10 used") in one round trip.
    """
    user_id = await get_user_id(request, db)
    
    raw_memories = await get_all_user_memories(
        db, user_id, include_superseded=include_superseded
    )
    
    # Convert to API models. The service layer returns dicts; the API layer
    # wraps in Pydantic for response validation.
    items = [
        MemoryItem(
            id=m["id"],
            content=m["content"],
            category=m["category"],
            confidence=m["confidence"],
            status=m["status"],
            created_at=m.get("created_at"),
            updated_at=m.get("updated_at")
        )
        for m in raw_memories
    ]
    
    active_count = await count_active_memories(db, user_id)
    is_pro = await _is_pro_user(db, user_id)
    paused = await _is_paused(db, user_id)
    cap = 10000 if is_pro else FREE_TIER_MEMORY_CAP
    
    return MemoriesListResponse(
        memories=items,
        total=len(items),
        active_count=active_count,
        cap=cap,
        is_pro=is_pro,
        paused=paused
    )


@router.put("/{memory_id}", response_model=MemoryItem)
async def edit_memory(
    memory_id: str,
    body: UpdateMemoryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Edit the content of a single memory. Useful when extraction got the
    fact slightly wrong ("user is vegan" when user is vegetarian).
    
    Validation:
        - content stripped length must be 1-500 chars
        - memory must belong to this user (enforced in service layer)
        - memory must be active (can't edit deleted/superseded ones)
    """
    user_id = await get_user_id(request, db)
    
    new_content = (body.content or "").strip()
    if not new_content:
        raise HTTPException(
            status_code=400,
            detail="Content cannot be empty. Use DELETE to remove a memory."
        )
    if len(new_content) > 500:
        raise HTTPException(
            status_code=400,
            detail=f"Content too long ({len(new_content)} chars). Max 500."
        )
    
    success = await update_memory(db, user_id, memory_id, new_content)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Memory not found, doesn't belong to you, or is not active."
        )
    
    # Return the updated memory by re-reading it. Slightly less efficient
    # than constructing the response from inputs, but guarantees we return
    # whatever the DB triggers (e.g. updated_at) actually wrote.
    result = await db.execute(
        text("""
            SELECT id, content, category, confidence, status, created_at, updated_at
            FROM user_memories
            WHERE id = :id AND user_id = :user_id
        """),
        {"id": memory_id, "user_id": user_id}
    )
    row = result.fetchone()
    if not row:
        # Edge case: the row was deleted between update and re-read.
        raise HTTPException(status_code=404, detail="Memory disappeared")
    
    logger.info(f"#38 User {user_id[:8]} edited memory {memory_id[:8]}")
    
    return MemoryItem(
        id=str(row[0]),
        content=row[1],
        category=row[2],
        confidence=float(row[3]),
        status=row[4],
        created_at=row[5].isoformat() if row[5] else None,
        updated_at=row[6].isoformat() if row[6] else None
    )


@router.delete("/{memory_id}")
async def delete_single_memory(
    memory_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Soft-delete a single memory. Marks status='deleted' but keeps the row
    briefly so we could implement undo later.
    """
    user_id = await get_user_id(request, db)
    success = await delete_memory(db, user_id, memory_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Memory not found or doesn't belong to you."
        )
    
    logger.info(f"#38 User {user_id[:8]} deleted memory {memory_id[:8]}")
    return {"status": "deleted", "memory_id": memory_id}


@router.delete("")
async def delete_all_user_memories(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    GDPR "forget me" — soft-delete ALL of the user's memories.
    
    Returns count of memories cleared. Idempotent — safe to call repeatedly.
    """
    user_id = await get_user_id(request, db)
    count = await delete_all_memories(db, user_id)
    return {
        "status": "deleted_all",
        "count": count
    }


@router.get("/settings", response_model=MemorySettingsResponse)
async def get_memory_settings(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Read the user's memory preferences (pause state, Pro status, cap, count).
    
    Used by the settings panel to render the toggle and cap counter.
    """
    user_id = await get_user_id(request, db)
    paused = await _is_paused(db, user_id)
    is_pro = await _is_pro_user(db, user_id)
    active_count = await count_active_memories(db, user_id)
    return _build_settings_response(paused, is_pro, active_count)


@router.put("/settings", response_model=MemorySettingsResponse)
async def update_memory_settings(
    body: UpdateSettingsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Update memory preferences. Only `paused` is currently writable;
    is_pro is derived from the subscription state (read-only here).
    
    A null `paused` field means "leave it as it is" — the request is then
    a no-op that just returns current state. Useful for partial updates.
    """
    user_id = await get_user_id(request, db)
    
    if body.paused is not None:
        prefs = await _get_preferences(db, user_id)
        prefs["memory_collection_paused"] = bool(body.paused)
        await _save_preferences(db, user_id, prefs)
        logger.info(
            f"#38 User {user_id[:8]} set memory_collection_paused = {body.paused}"
        )
    
    paused = await _is_paused(db, user_id)
    is_pro = await _is_pro_user(db, user_id)
    active_count = await count_active_memories(db, user_id)
    return _build_settings_response(paused, is_pro, active_count)