"""
OmniAI Backend - v0.7.0
Universal AI Interface with Chat, Files, Export, Auth, Gmail, Calendar
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from datetime import datetime
import logging
import os

# Import our modules
from utils.config import settings
from services.llm import llm_service

# Import ALL routers
from api.capabilities import router as capabilities_router
from api.chat_enhanced import router as chat_enhanced_router
from api.files import router as files_router
from api.export import router as export_router
from api.messages import router as messages_router
from api.auth import router as auth_router

# Optional routers
try:
    from api.chat import router as chat_router
    HAS_CHAT_ROUTER = True
except ImportError:
    HAS_CHAT_ROUTER = False

try:
    from api.code import router as code_router
    HAS_CODE_ROUTER = True
except ImportError:
    HAS_CODE_ROUTER = False

# Gmail router
try:
    from api.gmail import router as gmail_router
    HAS_GMAIL_ROUTER = True
    logging.getLogger(__name__).info("✅ Gmail router loaded")
except ImportError as e:
    HAS_GMAIL_ROUTER = False
    logging.getLogger(__name__).warning(f"⚠️ Gmail router not loaded: {e}")

# Calendar router — #29
try:
    from api.calendar import router as calendar_router
    HAS_CALENDAR_ROUTER = True
    logging.getLogger(__name__).info("✅ Calendar router loaded")
except ImportError as e:
    HAS_CALENDAR_ROUTER = False
    logging.getLogger(__name__).warning(f"⚠️ Calendar router not loaded: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the app
app = FastAPI(
    title="OmniAI API",
    description="The Universal AI Interface - Now with Gmail + Calendar!",
    version="0.7.0",
    debug=settings.DEBUG
)

# ========================================
# CORS MIDDLEWARE
# ========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================
# INCLUDE ALL ROUTERS
# ========================================

app.include_router(capabilities_router)
app.include_router(chat_enhanced_router)
app.include_router(files_router)

if HAS_CHAT_ROUTER:
    app.include_router(chat_router)

if HAS_CODE_ROUTER:
    app.include_router(code_router)

app.include_router(export_router)
app.include_router(messages_router)
app.include_router(auth_router)

if HAS_GMAIL_ROUTER:
    app.include_router(gmail_router)

if HAS_CALENDAR_ROUTER:
    app.include_router(calendar_router)

# ========================================
# STATIC FILES (Frontend)
# ========================================
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path, html=True), name="frontend")
    logger.info(f"📁 Frontend mounted from: {frontend_path}")


# ========================================
# REQUEST/RESPONSE MODELS
# ========================================

class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"

class ChatResponse(BaseModel):
    response: str
    model: str
    timestamp: str


# ========================================
# STARTUP EVENT
# ========================================

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting OmniAI Backend v0.7.0...")
    try:
        await llm_service.initialize()
        logger.info("✅ LLM service ready!")
    except Exception as e:
        logger.error(f"❌ LLM initialization failed: {e}")


# ========================================
# ROOT ENDPOINTS
# ========================================

@app.get("/")
async def root():
    return {
        "message": "🚀 Welcome to OmniAI!",
        "status": "running",
        "version": "0.7.0",
        "ai_ready": llm_service.initialized,
        "model": settings.MODEL_NAME,
        "features": [
            "Chat with AI",
            "Web Search",
            "Streaming Responses",
            "File Upload & Processing",
            "Code Execution",
            "Conversation Export",
            "Message Edit/Delete",
            "Full-Text Search",
            "Mobile Responsive",
            "User Authentication",
            "Gmail Integration",
            "Google Calendar Integration",
        ],
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "ai_ready": llm_service.initialized,
        "model": settings.MODEL_NAME
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        ai_response = await llm_service.generate(
            prompt=request.message,
            system_prompt="You are OmniAI, a helpful AI assistant. Be concise and friendly.",
            temperature=0.7,
            max_tokens=512
        )
        return ChatResponse(
            response=ai_response,
            model=settings.MODEL_NAME,
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")


@app.get("/config")
async def get_config():
    return {
        "api_version": "0.7.0",
        "debug_mode": settings.DEBUG,
        "model_name": settings.MODEL_NAME,
        "ai_initialized": llm_service.initialized
    }


# ========================================
# RUN SERVER
# ========================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 OmniAI Backend - v0.7.0")
    print("=" * 60)
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)