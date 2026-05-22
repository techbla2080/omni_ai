"""
Settings API — User preferences and customization.

#37 — Custom System Prompts (Pro feature):
Lets users save their own system prompt that gets prepended to every chat.
Stored at users.preferences.custom_system_prompt as JSONB.

Endpoints:
  GET    /api/v1/settings/system-prompt   — fetch current custom prompt
  PUT    /api/v1/settings/system-prompt   — save/update custom prompt
  DELETE /api/v1/settings/system-prompt   — clear custom prompt (back to default)

All endpoints require JWT authentication (Authorization: Bearer <token>).
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from api.pro_gate import require_pro
from utils.sanitize import sanitize_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


# ============================================================================
# Request/Response Models
# ============================================================================

# Hard limits to prevent abuse and runaway prompt costs.
# 2000 chars ≈ 500 tokens — generous (Twitter-thread length) but bounded.
# Every chat request burns these tokens, so we don't want anything bigger.
MAX_PROMPT_LENGTH = 2000
MIN_PROMPT_LENGTH = 1  # at least one non-whitespace character


class SystemPromptRequest(BaseModel):
    """Body for PUT /system-prompt — save or update the user's custom prompt."""
    prompt: str = Field(..., description="Custom system prompt text", max_length=MAX_PROMPT_LENGTH * 2)
    # max_length on Field is a soft check; we re-validate in the handler with
    # the real MAX_PROMPT_LENGTH limit and a friendly error message. Pydantic's
    # default error is ugly.


class SystemPromptResponse(BaseModel):
    """Response shape for GET / PUT — current state of the custom prompt."""
    prompt: Optional[str] = None
    is_set: bool = False
    char_count: int = 0
    max_chars: int = MAX_PROMPT_LENGTH


# ============================================================================
# Auth helper
# ============================================================================

async def get_user_id(request: Request, db: AsyncSession) -> str:
    """
    Extract authenticated user_id from JWT.
    Settings endpoints are gated behind auth — anonymous users can't save prompts.
    """
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ============================================================================
# Helpers — read/write user preferences JSONB column safely
# ============================================================================

async def _get_preferences(db: AsyncSession, user_id: str) -> dict:
    """
    Fetch the user's preferences JSONB. Returns empty dict if user not found
    or preferences is null. Always safe to call.
    """
    result = await db.execute(
        text("SELECT preferences FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    row = result.fetchone()
    if not row or row[0] is None:
        return {}
    raw = row[0]
    # SQLAlchemy may return either a parsed dict (JSONB native) or a string.
    # Handle both shapes defensively.
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


async def _save_preferences(db: AsyncSession, user_id: str, prefs: dict):
    """
    Persist the full preferences dict back to the users table.
    Uses parameterised JSON so we don't need to worry about quoting.
    """
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


def _build_response(prompt: Optional[str]) -> SystemPromptResponse:
    """Build the canonical response shape from a prompt value."""
    if prompt and isinstance(prompt, str):
        stripped = prompt.strip()
        if stripped:
            return SystemPromptResponse(
                prompt=stripped,
                is_set=True,
                char_count=len(stripped),
                max_chars=MAX_PROMPT_LENGTH
            )
    return SystemPromptResponse(
        prompt=None,
        is_set=False,
        char_count=0,
        max_chars=MAX_PROMPT_LENGTH
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/system-prompt", response_model=SystemPromptResponse)
async def get_system_prompt(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the user's current custom system prompt.
    
    Returns:
        prompt:      the custom prompt string, or null if none set
        is_set:      true if a non-empty prompt is configured
        char_count:  length of the current prompt (0 if not set)
        max_chars:   the maximum allowed length (for frontend counter display)
    """
    user_id = await get_user_id(request, db)
    prefs = await _get_preferences(db, user_id)
    return _build_response(prefs.get("custom_system_prompt"))


@router.put("/system-prompt", response_model=SystemPromptResponse)
async def set_system_prompt(
    body: SystemPromptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _pro: None = Depends(require_pro("custom_prompt")),
):
    """
    Save or update the user's custom system prompt.
    
    Validation:
        - Stripped length must be between 1 and 2000 chars
        - Empty/whitespace-only prompts are rejected (use DELETE to clear)
    
    The prompt is merged into the user's existing preferences JSONB so other
    settings (future: theme, default mode, etc.) aren't clobbered.
    """
    user_id = await get_user_id(request, db)
    
    # Validate the prompt
    prompt = (body.prompt or "").strip()
    
    if len(prompt) < MIN_PROMPT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="Prompt cannot be empty. Use DELETE to clear your custom prompt."
        )
    
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is too long ({len(prompt)} chars). Maximum is {MAX_PROMPT_LENGTH} characters."
        )
    
    # Merge into existing preferences (don't clobber other settings)
    prefs = await _get_preferences(db, user_id)
    prefs["custom_system_prompt"] = sanitize_prompt(prompt, max_length=2000)
    await _save_preferences(db, user_id, prefs)
    
    logger.info(f"#37 Custom prompt saved for user {user_id[:8]}... ({len(prompt)} chars)")
    
    return _build_response(prompt)


@router.delete("/system-prompt", response_model=SystemPromptResponse)
async def delete_system_prompt(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Clear the user's custom system prompt.
    
    Removes the custom_system_prompt key from preferences without disturbing
    any other preferences. Returns the empty state (is_set: false).
    
    Idempotent — safe to call even if no prompt is currently set.
    """
    user_id = await get_user_id(request, db)
    
    prefs = await _get_preferences(db, user_id)
    
    if "custom_system_prompt" in prefs:
        del prefs["custom_system_prompt"]
        await _save_preferences(db, user_id, prefs)
        logger.info(f"#37 Custom prompt cleared for user {user_id[:8]}...")
    
    return _build_response(None)