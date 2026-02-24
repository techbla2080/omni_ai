"""
OmniAI Backend - Steps 1-62 Complete
Universal AI Interface with Chat, Files, Export, Auth
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
from api.export import router as export_router          # Step 51 + 54
from api.messages import router as messages_router      # Step 52
from api.auth import router as auth_router              # Steps 56-62

# Optional routers (comment out if not yet created)
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the app
app = FastAPI(
    title="OmniAI API",
    description="The Universal AI Interface - Now with Auth & Export!",
    version="0.6.0",
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

# Core routers (Steps 1-50)
app.include_router(capabilities_router)
app.include_router(chat_enhanced_router)
app.include_router(files_router)

if HAS_CHAT_ROUTER:
    app.include_router(chat_router)

if HAS_CODE_ROUTER:
    app.include_router(code_router)

# New routers (Steps 51-62)
app.include_router(export_router)       # Export + Search
app.include_router(messages_router)     # Edit/Delete messages
app.include_router(auth_router)         # Auth system

# ========================================
# STATIC FILES (Frontend)
# ========================================
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path, html=True), name="frontend")
    logger.info(f"📁 Frontend mounted from: {frontend_path}")


# ========================================
# AUTH MIDDLEWARE (Step 61)
# ========================================
# NOTE: Uncomment AFTER you build the login UI!
# Otherwise all API calls will require auth tokens.
#
# from starlette.middleware.base import BaseHTTPMiddleware
#
# class AuthMiddleware(BaseHTTPMiddleware):
#     PUBLIC_ROUTES = [
#         "/", "/health", "/docs", "/openapi.json", "/frontend",
#         "/api/v1/auth/register", "/api/v1/auth/login",
#         "/api/v1/auth/refresh", "/api/v1/auth/forgot-password",
#         "/api/v1/auth/reset-password", "/api/v1/auth/google",
#         "/api/v1/auth/google/callback",
#     ]
#
#     async def dispatch(self, request: Request, call_next):
#         path = request.url.path
#         if any(path.startswith(route) for route in self.PUBLIC_ROUTES):
#             return await call_next(request)
#         if path.startswith("/frontend") or path.startswith("/static"):
#             return await call_next(request)
#         auth = request.headers.get("Authorization")
#         if not auth or not auth.startswith("Bearer "):
#             from fastapi.responses import JSONResponse
#             return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
#         return await call_next(request)
#
# app.add_middleware(AuthMiddleware)


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
    """Initialize services on startup"""
    logger.info("🚀 Starting OmniAI Backend...")
    try:
        await llm_service.initialize()
        logger.info("✅ LLM service ready!")
    except Exception as e:
        logger.error(f"❌ LLM initialization failed: {e}")
        logger.error("Make sure Ollama is running: ollama serve")


# ========================================
# ROOT ENDPOINTS
# ========================================

@app.get("/")
async def root():
    """Welcome endpoint"""
    return {
        "message": "🚀 Welcome to OmniAI!",
        "status": "running",
        "version": "0.6.0 (Steps 1-62)",
        "ai_ready": llm_service.initialized,
        "model": settings.MODEL_NAME,
        "features": [
            "Chat with AI",
            "Web Search",
            "Multi-Model Support",
            "Response Regeneration",
            "Streaming Responses",
            "Feedback System",
            "File Upload & Processing",
            "Code Execution",
            "Conversation Export",       # Step 51
            "Message Edit/Delete",       # Step 52
            "Keyboard Shortcuts",        # Step 53
            "Full-Text Search",          # Step 54
            "Mobile Responsive",         # Step 55
            "User Authentication",       # Steps 56-62
        ],
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "ai_ready": llm_service.initialized,
        "model": settings.MODEL_NAME
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Basic chat endpoint (legacy - use /api/v1/chat instead)"""
    try:
        logger.info(f"💬 Chat request from {request.user_id}: {request.message[:50]}...")

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
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)}"
        )


@app.get("/config")
async def get_config():
    """Show configuration"""
    return {
        "api_version": "0.6.0",
        "debug_mode": settings.DEBUG,
        "model_name": settings.MODEL_NAME,
        "ai_initialized": llm_service.initialized
    }


# ========================================
# RUN SERVER
# ========================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 OmniAI Backend - v0.6.0 (Steps 1-62)")
    print("=" * 60)
    print(f"📡 Host: {settings.API_HOST}")
    print(f"🔌 Port: {settings.API_PORT}")
    print(f"🤖 Model: {settings.MODEL_NAME}")
    print("=" * 60)
    print("📦 Routers: capabilities, chat, files, export, messages, auth")
    print("=" * 60)
    print("⚠️  Make sure Ollama + Docker are running!")
    print("=" * 60)

    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT
    )