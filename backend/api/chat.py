"""
Chat API - Now with Redis context caching!
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import logging

from services.llm import llm_service
from services.context_manager import context_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    model: str
    conversation_id: str
    timestamp: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with AI - Now with conversation context!
    """
    try:
        # Generate conversation ID if new
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        logger.info(f"💬 Chat request from {request.user_id}")
        logger.info(f"📝 Message: {request.message[:50]}...")
        logger.info(f"🔑 Conversation: {conversation_id}")
        
        # Build context from Redis cache
        context = context_manager.build_context(
            conversation_id,
            request.message,
            max_context_messages=5
        )
        
        # Create system prompt with context
        if context:
            system_prompt = f"""You are OmniAI, a helpful AI assistant.

{context}

Use the conversation history above to provide contextual responses.
Answer the user's current question naturally."""
        else:
            system_prompt = "You are OmniAI, a helpful AI assistant. Be concise and friendly."
        
        # Generate AI response
        ai_response = await llm_service.generate(
            prompt=request.message,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=512
        )
        
        # Cache user message
        context_manager.cache_message(conversation_id, {
            "role": "user",
            "content": request.message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Cache AI response
        context_manager.cache_message(conversation_id, {
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info("✅ Response generated and cached")
        
        return ChatResponse(
            response=ai_response,
            model=llm_service.model_name,
            conversation_id=conversation_id,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)}"
        )


@router.get("/cache/stats")
async def cache_stats():
    """Get Redis cache statistics"""
    return context_manager.get_stats()