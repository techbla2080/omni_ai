"""
OmniAI Intent Classification API (Task #33.5)
Exposes the AI intent classifier to the frontend.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from services.intent_classifier import classify_intent
from database.database import get_db

logger = logging.getLogger(__name__)


class ClassifyRequest(BaseModel):
    message: str
    mode: Optional[str] = "normal"


router = APIRouter(prefix="/api/v1/intent", tags=["intent"])


@router.post("/classify")
async def classify(
    request: Request,
    body: ClassifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Classify a user message into structured intent JSON.
    
    Returns:
        {
            "domain": "gmail" | "calendar" | "code" | "general",
            "action": "<action_name>",
            "params": { ... },
            "confidence": 0.0-1.0
        }
    """
    # Auth check (require logged-in user)
    try:
        from api.auth import get_current_user
        user_id = await get_current_user(request, db)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        result = await classify_intent(body.message.strip(), body.mode or "normal")
        return result
    except Exception as e:
        logger.error(f"Intent classification error: {e}")
        # Return low-confidence fallback instead of erroring out
        # — frontend will fall back to regex
        return {
            "domain": "general",
            "action": "chat",
            "params": {},
            "confidence": 0.0,
            "_error": str(e)
        }