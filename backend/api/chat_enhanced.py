"""
Enhanced Chat API with Capability Detection + Conversation Persistence + Redis Context
NOW WITH: Auto-generated titles, title editing, WEB SEARCH, SMART MODEL ROUTING, REGENERATION, STREAMING, FEEDBACK, FILE CONTEXT, AND AI MODE SYSTEM!
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pathlib import Path
import uuid
import re
import json

# Import LLM service, database, context manager, web search, model router, AND FILE CONTEXT
from services.llm import llm_service
from services.context_manager import context_manager
from services.web_search import web_search_service
from services.model_router import model_router
from services.file_context import file_context_service
from database import get_db

router = APIRouter(prefix="/api/v1", tags=["chat"])


# ============================================================================
# AI MODE SYSTEM — #25
# ============================================================================

VALID_MODES = {"normal", "email", "calendar", "code"}
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_prompt_cache: Dict[str, str] = {}


def load_mode_prompt(mode: str) -> str:
    """Load system prompt for the given mode from backend/prompts/{mode}.md"""
    if mode not in VALID_MODES:
        mode = "normal"

    if mode in _prompt_cache:
        return _prompt_cache[mode]

    prompt_file = PROMPTS_DIR / f"{mode}.md"
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        _prompt_cache[mode] = content
        print(f"✅ Loaded {mode} mode prompt from {prompt_file}")
        return content
    except FileNotFoundError:
        print(f"⚠️ Prompt file not found: {prompt_file}, using fallback")
        fallback = "You are OmniAI, a helpful AI assistant."
        _prompt_cache[mode] = fallback
        return fallback


async def get_conversation_mode(db: AsyncSession, conversation_id: str) -> str:
    """Get the current mode of a conversation, defaults to 'normal'"""
    if not conversation_id:
        return "normal"
    try:
        result = await db.execute(
            text("SELECT mode FROM conversations WHERE id = :conv_id"),
            {"conv_id": conversation_id}
        )
        row = result.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        print(f"⚠️ Could not fetch conversation mode: {e}")
    return "normal"


def build_system_prompt(mode: str, file_context: str = "", search_context: str = "", conv_context: str = "") -> str:
    """Build the full system prompt based on mode and available context"""
    system_prompt = load_mode_prompt(mode)

    if file_context:
        system_prompt += "\n\n--- USER'S FILE CONTENT ---"
        system_prompt += f"\n{file_context}"
        system_prompt += "\n--- END FILE CONTENT ---"
        system_prompt += "\n\nIMPORTANT: The user is asking about these files. Use this content to answer their question."

    if search_context:
        system_prompt += "\n\n--- CURRENT WEB SEARCH RESULTS ---"
        system_prompt += search_context
        system_prompt += "\n--- END SEARCH RESULTS ---"
        system_prompt += "\n\nIMPORTANT: Base your answer on these current search results."

    if conv_context:
        system_prompt += f"\n\n--- CONVERSATION HISTORY ---\n{conv_context}"

    return system_prompt


# ============================================================================
# Pydantic Models
# ============================================================================

class ChatRequest(BaseModel):
    """Enhanced chat request"""
    message: str
    user_id: str = "anonymous"
    conversation_id: Optional[str] = None
    file_ids: Optional[List[str]] = None  # Attach specific files
    mode: Optional[str] = None  # NEW — for new conversations, or to override


class Suggestion(BaseModel):
    """Action suggestion"""
    text: str
    action: str


class ChatResponse(BaseModel):
    """Enhanced chat response with capability detection"""
    response: str
    conversation_id: str
    timestamp: str
    response_type: str = "chat"
    suggestions: List[Suggestion] = []
    capabilities: Optional[List[Dict]] = None
    model: str = "llama3.2:1b"
    latency_ms: Optional[int] = None
    search_performed: bool = False
    search_results_count: Optional[int] = None
    model_selection_reason: Optional[str] = None
    model_quality_score: Optional[int] = None
    files_used: Optional[int] = None
    mode: Optional[str] = None  # NEW


class ConversationResponse(BaseModel):
    """Conversation with messages"""
    id: str
    title: Optional[str]
    messages: List[Dict]
    created_at: str
    updated_at: str
    mode: Optional[str] = "normal"  # NEW


class UpdateTitleRequest(BaseModel):
    """Request to update conversation title"""
    title: str


class UpdateModeRequest(BaseModel):
    """Request to update conversation mode"""
    mode: str


class RegenerateRequest(BaseModel):
    """Request to regenerate a response"""
    conversation_id: str
    message_id: str
    model: Optional[str] = None
    temperature: Optional[float] = None


class FeedbackRequest(BaseModel):
    """Request to submit feedback on a response"""
    message_id: str
    conversation_id: str
    rating: int
    comment: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def generate_title_from_message(message: str) -> str:
    """Generate a smart title from the first message"""

    message = message.strip()

    prefixes = [
        "can you", "could you", "please", "help me", "i want to",
        "i need to", "how do i", "how to", "what is", "what are"
    ]

    lower_msg = message.lower()
    for prefix in prefixes:
        if lower_msg.startswith(prefix):
            message = message[len(prefix):].strip()
            break

    if message:
        message = message[0].upper() + message[1:]

    if len(message) > 50:
        message = message[:47] + "..."

    message = re.sub(r'[?.!]+$', '', message)

    return message or "New Conversation"


def detect_file_reference(message: str) -> bool:
    """Detect if user is asking about files"""

    triggers = [
        "file", "document", "pdf", "upload", "attached", "image",
        "spreadsheet", "excel", "csv", "word", "docx",
        "summarize", "analyze", "read", "what does", "extract",
        "the document", "this file", "my file", "the pdf",
        "uploaded", "attachment"
    ]

    message_lower = message.lower()

    for trigger in triggers:
        if trigger in message_lower:
            return True

    return False


# ============================================================================
# Capability Detection
# ============================================================================

def detect_capability_query(message: str) -> bool:
    """Detect if user is asking about capabilities"""

    triggers = [
        "what can you do",
        "what can u do",
        "what are you capable of",
        "what are your capabilities",
        "show me features",
        "what features",
        "help me discover",
        "show capabilities",
        "list capabilities",
        "what can i do with you",
        "what do you offer",
        "show me what you can do",
        "tell me what you can do",
        "your features",
        "your capabilities"
    ]

    message_lower = message.lower().strip()

    for trigger in triggers:
        if trigger in message_lower:
            return True

    return False


def get_mock_capabilities() -> List[Dict]:
    """Return abbreviated capability list for chat responses"""
    return [
        {"id": "cap-001", "name": "Read Emails", "category": "email", "description": "View and read your emails", "example": "Show me unread emails"},
        {"id": "cap-002", "name": "Send Emails", "category": "email", "description": "Compose and send emails", "example": "Send email to john@example.com"},
        {"id": "cap-004", "name": "View Calendar", "category": "calendar", "description": "Check your schedule", "example": "What's on my calendar today?"},
        {"id": "cap-005", "name": "Schedule Meetings", "category": "calendar", "description": "Create calendar events", "example": "Schedule meeting with Alex at 2pm"},
        {"id": "cap-006", "name": "Find Products", "category": "shopping", "description": "Search for products", "example": "Find wireless headphones under $100"},
        {"id": "cap-009", "name": "Web Research", "category": "research", "description": "Deep web research", "example": "Research quantum computing"},
        {"id": "cap-011", "name": "Task Management", "category": "productivity", "description": "Create and track tasks", "example": "Add finish report to my tasks"},
        {"id": "cap-018", "name": "Code Generation", "category": "coding", "description": "Generate code snippets", "example": "Write Python function to sort list"}
    ]


def format_capability_response() -> str:
    """Format capabilities into a natural language response"""

    response = """I can help you with many things! Here are my main capabilities:

📧 **Email Management**
- Read and organize your emails
- Send emails with AI assistance
- Draft professional emails

📅 **Calendar & Scheduling**
- View your schedule
- Create and manage meetings
- Smart scheduling suggestions

🛍️ **Shopping & Products**
- Find and compare products
- Track prices
- Make secure purchases

🔍 **Research & Information**
- Deep web research (I can search the web in real-time!)
- Fact checking and verification
- Information synthesis
- Get current news, prices, weather

📄 **File Analysis** ← NEW!
- Read and summarize PDFs
- Extract text from images (OCR)
- Analyze Word documents and Excel files
- Process CSV data

✅ **Productivity Tools**
- Task management
- Note taking with smart tags
- Reminders and alerts

💻 **Coding Assistance**
- Code generation in multiple languages
- Debug and fix errors
- Code explanations

💰 **Finance**
- Expense tracking
- Budget management

✈️ **Travel Planning**
- Trip planning and itineraries
- Travel recommendations

Click on any capability in the panel to try it, or just ask me directly! For example, try: "What's the latest AI news?" or "Summarize my uploaded PDF"
"""

    return response


def create_capability_suggestions() -> List[Suggestion]:
    """Create interactive suggestions for capabilities"""

    return [
        Suggestion(text="🔍 Search the web", action="What's the latest AI news?"),
        Suggestion(text="📧 Check my emails", action="Show me unread emails"),
        Suggestion(text="📅 View my calendar", action="What's on my calendar today?"),
        Suggestion(text="📄 Analyze file", action="Summarize the uploaded document"),
        Suggestion(text="💻 Generate code", action="Write a Python function to sort a list")
    ]


# ============================================================================
# Database Functions
# ============================================================================

async def get_or_create_conversation(
    db: AsyncSession,
    conversation_id: Optional[str],
    user_id: str,
    first_message: str = None,
    initial_mode: str = "normal"
) -> tuple:
    """Get existing conversation or create new one with auto-generated title and mode"""

    if conversation_id:
        result = await db.execute(
            text("SELECT id, title, mode FROM conversations WHERE id = :conv_id"),
            {"conv_id": conversation_id}
        )
        existing = result.fetchone()

        if existing:
            await db.execute(
                text("UPDATE conversations SET updated_at = NOW() WHERE id = :conv_id"),
                {"conv_id": conversation_id}
            )
            await db.commit()
            return str(existing[0]), existing[1], existing[2] or "normal"

    new_id = str(uuid.uuid4())
    title = generate_title_from_message(first_message) if first_message else "New Conversation"

    if initial_mode not in VALID_MODES:
        initial_mode = "normal"

    await db.execute(
        text("""
            INSERT INTO conversations (id, user_id, title, mode, created_at, updated_at)
            VALUES (:id, :user_id, :title, :mode, NOW(), NOW())
        """),
        {"id": new_id, "user_id": None, "title": title, "mode": initial_mode}
    )
    await db.commit()

    return new_id, title, initial_mode


async def save_message(db: AsyncSession, conversation_id: str, role: str, content: str, model: str = None, latency_ms: int = None):
    """Save a message to the database"""

    message_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO messages (id, conversation_id, role, content, model, latency_ms, created_at)
            VALUES (:id, :conv_id, :role, :content, :model, :latency_ms, NOW())
        """),
        {
            "id": message_id,
            "conv_id": conversation_id,
            "role": role,
            "content": content,
            "model": model,
            "latency_ms": latency_ms
        }
    )
    await db.commit()

    return message_id


async def get_conversation_messages(db: AsyncSession, conversation_id: str) -> List[Dict]:
    """Get all messages for a conversation"""

    result = await db.execute(
        text("""
            SELECT id, role, content, model, latency_ms, created_at
            FROM messages
            WHERE conversation_id = :conv_id
            ORDER BY created_at ASC
        """),
        {"conv_id": conversation_id}
    )

    messages = []
    for row in result.fetchall():
        messages.append({
            "id": str(row[0]),
            "role": row[1],
            "content": row[2],
            "model": row[3],
            "latency_ms": row[4],
            "created_at": row[5].isoformat() if row[5] else None
        })

    return messages


# ============================================================================
# Chat Endpoint with Persistence + Context + Web Search + SMART MODEL ROUTING + FILES + MODE
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def enhanced_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced chat endpoint with:
    - Real LLM responses
    - Capability detection
    - Conversation persistence to PostgreSQL
    - Redis context memory (AI REMEMBERS!)
    - Auto-generated conversation titles
    - WEB SEARCH for current information!
    - SMART MODEL ROUTING for optimal quality/speed!
    - FILE CONTEXT for document analysis!
    - AI MODE SYSTEM for focused responses! ← NEW!
    """

    start_time = datetime.utcnow()

    try:
        initial_mode = request.mode if request.mode in VALID_MODES else "normal"

        conversation_id, title, current_mode = await get_or_create_conversation(
            db,
            request.conversation_id,
            request.user_id,
            request.message,
            initial_mode=initial_mode
        )

        # Save user message to database
        await save_message(db, conversation_id, "user", request.message)

        # Cache message in Redis for context
        context_manager.add_message(conversation_id, "user", request.message)

        # Check if this is a capability query
        is_capability_query = detect_capability_query(request.message)

        if is_capability_query:
            response_text = format_capability_response()
            suggestions = create_capability_suggestions()
            capabilities = get_mock_capabilities()

            await save_message(db, conversation_id, "assistant", response_text, "llama3.2:1b", 0)
            context_manager.add_message(conversation_id, "assistant", response_text)

            return ChatResponse(
                response=response_text,
                conversation_id=conversation_id,
                timestamp=datetime.utcnow().isoformat(),
                response_type="capability_list",
                suggestions=suggestions,
                capabilities=capabilities,
                model="llama3.2:1b",
                latency_ms=0,
                mode=current_mode
            )

        # ============================================
        # FILE CONTEXT INTEGRATION
        # ============================================
        file_context = ""
        files_used = 0

        if request.file_ids or detect_file_reference(request.message):
            print(f"📎 File context requested")

            file_context = await file_context_service.get_file_context(
                db=db,
                file_ids=request.file_ids,
                conversation_id=conversation_id
            )

            if file_context:
                files_used = file_context.count("=== File:")
                print(f"✅ Added {files_used} file(s) to context")

        # ============================================
        # WEB SEARCH INTEGRATION
        # ============================================
        search_context = ""
        search_performed = False
        search_results_count = 0

        if web_search_service.should_search(request.message):
            print(f"🔍 Web search triggered for: '{request.message}'")

            search_query = web_search_service.extract_search_query(request.message)
            print(f"   Searching for: '{search_query}'")

            search_results = await web_search_service.search(
                search_query,
                count=5,
                freshness="pw"
            )

            if search_results.get("results"):
                search_performed = True
                search_results_count = len(search_results["results"])
                search_context = "\n\n" + web_search_service.format_results_for_llm(search_results)
                print(f"✅ Found {search_results_count} search results")

        # Get conversation context from Redis
        conv_context = context_manager.format_context_for_llm(conversation_id)

        # ============================================
        # BUILD SYSTEM PROMPT BASED ON MODE — #25
        # ============================================

        system_prompt = build_system_prompt(
            mode=current_mode,
            file_context=file_context,
            search_context=search_context,
            conv_context=conv_context
        )

        print(f"🎯 Mode: {current_mode}")

        # ============================================
        # SMART MODEL SELECTION
        # ============================================

        model_selection = model_router.choose_model(
            query=request.message,
            has_search_results=search_performed,
            has_files=files_used > 0,
            context_length=len(system_prompt)
        )

        chosen_model = model_selection["model"]
        selection_reason = model_selection["reason"]

        print(f"🤖 Model selected: {chosen_model}")
        print(f"   Reason: {selection_reason}")

        # ============================================
        # GENERATE AI RESPONSE
        # ============================================

        ai_response = await llm_service.generate(
            prompt=request.message,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2000,
            model=chosen_model
        )

        model_used = chosen_model

        end_time = datetime.utcnow()
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        message_id = await save_message(db, conversation_id, "assistant", ai_response, model_used, latency_ms)
        context_manager.add_message(conversation_id, "assistant", ai_response)

        return ChatResponse(
            response=ai_response,
            conversation_id=conversation_id,
            timestamp=end_time.isoformat(),
            response_type="chat",
            suggestions=[],
            model=model_used,
            latency_ms=latency_ms,
            search_performed=search_performed,
            search_results_count=search_results_count,
            model_selection_reason=selection_reason,
            model_quality_score=model_selection['quality_score'],
            files_used=files_used,
            mode=current_mode
        )

    except Exception as e:
        print(f"❌ Chat error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)}"
        )


# ============================================================================
# STREAMING CHAT ENDPOINT — #15 Real token streaming + #25 Mode
# ============================================================================

@router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """Streaming chat endpoint using Server-Sent Events with AI Mode support"""

    async def generate():
        try:
            initial_mode = request.mode if request.mode in VALID_MODES else "normal"

            conversation_id, title, current_mode = await get_or_create_conversation(
                db,
                request.conversation_id,
                request.user_id,
                request.message,
                initial_mode=initial_mode
            )

            await save_message(db, conversation_id, "user", request.message)
            context_manager.add_message(conversation_id, "user", request.message)

            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id, 'mode': current_mode})}\n\n"

            # FILE CONTEXT
            file_context = ""
            files_used = 0

            if request.file_ids or detect_file_reference(request.message):
                yield f"data: {json.dumps({'type': 'status', 'message': 'Reading files...'})}\n\n"

                file_context = await file_context_service.get_file_context(
                    db=db,
                    file_ids=request.file_ids,
                    conversation_id=conversation_id
                )

                if file_context:
                    files_used = file_context.count("=== File:")
                    yield f"data: {json.dumps({'type': 'status', 'message': f'Loaded {files_used} file(s)'})}\n\n"

            # WEB SEARCH
            search_context = ""
            search_performed = False

            if web_search_service.should_search(request.message):
                yield f"data: {json.dumps({'type': 'status', 'message': 'Searching web...'})}\n\n"

                search_query = web_search_service.extract_search_query(request.message)
                search_results = await web_search_service.search(search_query, count=5, freshness="pw")

                if search_results.get("results"):
                    search_performed = True
                    search_context = "\n\n" + web_search_service.format_results_for_llm(search_results)
                    results_count = len(search_results["results"])
                    yield f"data: {json.dumps({'type': 'status', 'message': f'Found {results_count} results'})}\n\n"

            conv_context = context_manager.format_context_for_llm(conversation_id)

            # BUILD SYSTEM PROMPT BASED ON MODE — #25
            system_prompt = build_system_prompt(
                mode=current_mode,
                file_context=file_context,
                search_context=search_context,
                conv_context=conv_context
            )

            print(f"🎯 Stream mode: {current_mode}")

            model_selection = model_router.choose_model(
                query=request.message,
                has_search_results=search_performed,
                has_files=files_used > 0,
                context_length=len(system_prompt)
            )

            chosen_model = model_selection["model"]

            yield f"data: {json.dumps({'type': 'model', 'model': chosen_model})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating response...'})}\n\n"

            full_response = ""
            async for token in llm_service.generate_stream(
                prompt=request.message,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=2000,
                model=chosen_model
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            assistant_msg_id = await save_message(db, conversation_id, "assistant", full_response, chosen_model, 0)
            context_manager.add_message(conversation_id, "assistant", full_response)

            yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'files_used': files_used, 'message_id': assistant_msg_id, 'conversation_id': conversation_id, 'mode': current_mode})}\n\n"

        except Exception as e:
            print(f"❌ Stream error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================================
# RESPONSE REGENERATION
# ============================================================================

@router.post("/chat/regenerate", response_model=ChatResponse)
async def regenerate_response(
    request: RegenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Regenerate an AI response (respects conversation mode)"""

    start_time = datetime.utcnow()

    try:
        result = await db.execute(
            text("SELECT id, title, mode FROM conversations WHERE id = :conv_id"),
            {"conv_id": request.conversation_id}
        )
        conversation = result.fetchone()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        current_mode = conversation[2] or "normal"

        result = await db.execute(
            text("""
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = :conv_id
                AND created_at <= (
                    SELECT created_at FROM messages WHERE id = :msg_id
                )
                ORDER BY created_at ASC
            """),
            {"conv_id": request.conversation_id, "msg_id": request.message_id}
        )

        messages = result.fetchall()

        user_message = None
        for msg in reversed(messages):
            if msg[1] == "user":
                user_message = msg[2]
                break

        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")

        print(f"🔄 Regenerating response for: '{user_message[:50]}...' (mode: {current_mode})")

        file_context = ""
        files_used = 0

        if detect_file_reference(user_message):
            file_context = await file_context_service.get_file_context(
                db=db,
                conversation_id=request.conversation_id
            )
            if file_context:
                files_used = file_context.count("=== File:")

        search_context = ""
        search_performed = False
        search_results_count = 0

        if web_search_service.should_search(user_message):
            search_query = web_search_service.extract_search_query(user_message)
            search_results = await web_search_service.search(search_query, count=5, freshness="pw")

            if search_results.get("results"):
                search_performed = True
                search_results_count = len(search_results["results"])
                search_context = "\n\n" + web_search_service.format_results_for_llm(search_results)

        conv_context = context_manager.format_context_for_llm(request.conversation_id)

        # BUILD SYSTEM PROMPT BASED ON MODE — #25
        system_prompt = build_system_prompt(
            mode=current_mode,
            file_context=file_context,
            search_context=search_context,
            conv_context=conv_context
        )

        chosen_model = request.model if request.model else None

        if not chosen_model:
            model_selection = model_router.choose_model(
                query=user_message,
                has_search_results=search_performed,
                has_files=files_used > 0,
                context_length=len(system_prompt)
            )
            chosen_model = model_selection["model"]
            selection_reason = model_selection["reason"]
        else:
            selection_reason = "User selected model"

        ai_response = await llm_service.generate(
            prompt=user_message,
            system_prompt=system_prompt,
            temperature=request.temperature or 0.7,
            max_tokens=2000,
            model=chosen_model
        )

        end_time = datetime.utcnow()
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        await db.execute(
            text("DELETE FROM messages WHERE id = :msg_id"),
            {"msg_id": request.message_id}
        )
        await db.commit()

        await save_message(db, request.conversation_id, "assistant", ai_response, chosen_model, latency_ms)
        context_manager.add_message(request.conversation_id, "assistant", ai_response)

        quality_score = model_router.models.get(chosen_model, {}).get("quality", 4)

        return ChatResponse(
            response=ai_response,
            conversation_id=request.conversation_id,
            timestamp=end_time.isoformat(),
            response_type="chat",
            suggestions=[],
            model=chosen_model,
            latency_ms=latency_ms,
            search_performed=search_performed,
            search_results_count=search_results_count,
            model_selection_reason=selection_reason,
            model_quality_score=quality_score,
            files_used=files_used,
            mode=current_mode
        )

    except Exception as e:
        print(f"❌ Regenerate error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")


# ============================================================================
# FEEDBACK & QUALITY METRICS
# ============================================================================

@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submit feedback (thumbs up/down) for an AI response"""

    if request.rating not in [-1, 1]:
        raise HTTPException(status_code=400, detail="Rating must be -1 or 1")

    try:
        result = await db.execute(
            text("SELECT id FROM messages WHERE id = :msg_id"),
            {"msg_id": request.message_id}
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Message not found")

        await db.execute(
            text("DELETE FROM feedback WHERE message_id = :msg_id"),
            {"msg_id": request.message_id}
        )

        feedback_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO feedback (id, message_id, conversation_id, rating, comment, created_at)
                VALUES (:id, :msg_id, :conv_id, :rating, :comment, NOW())
            """),
            {
                "id": feedback_id,
                "msg_id": request.message_id,
                "conv_id": request.conversation_id,
                "rating": request.rating,
                "comment": request.comment
            }
        )
        await db.commit()

        emoji = "👍" if request.rating == 1 else "👎"
        print(f"{emoji} Feedback received for message {request.message_id[:8]}...")

        return {
            "status": "success",
            "feedback_id": feedback_id,
            "message_id": request.message_id,
            "rating": request.rating,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"❌ Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/stats")
async def get_feedback_stats(db: AsyncSession = Depends(get_db)):
    """Get overall feedback statistics"""

    try:
        result = await db.execute(text("SELECT * FROM feedback_stats"))
        stats = result.fetchone()

        if not stats:
            return {"thumbs_up": 0, "thumbs_down": 0, "total_feedback": 0, "satisfaction_rate": 0}

        return {
            "thumbs_up": stats[0] or 0,
            "thumbs_down": stats[1] or 0,
            "total_feedback": stats[2] or 0,
            "satisfaction_rate": float(stats[3]) if stats[3] else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/message/{message_id}")
async def get_message_feedback(message_id: str, db: AsyncSession = Depends(get_db)):
    """Get feedback for a specific message"""

    try:
        result = await db.execute(
            text("SELECT id, rating, comment, created_at FROM feedback WHERE message_id = :msg_id"),
            {"msg_id": message_id}
        )

        feedback = result.fetchone()

        if not feedback:
            return {"has_feedback": False}

        return {
            "has_feedback": True,
            "feedback_id": str(feedback[0]),
            "rating": feedback[1],
            "comment": feedback[2],
            "created_at": feedback[3].isoformat() if feedback[3] else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Conversation Management Endpoints
# ============================================================================

@router.get("/chat/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Get a conversation with all its messages (includes mode)"""

    result = await db.execute(
        text("SELECT id, title, created_at, updated_at, mode FROM conversations WHERE id = :conv_id"),
        {"conv_id": conversation_id}
    )
    conv = result.fetchone()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await get_conversation_messages(db, conversation_id)

    return ConversationResponse(
        id=str(conv[0]),
        title=conv[1],
        messages=messages,
        created_at=conv[2].isoformat() if conv[2] else None,
        updated_at=conv[3].isoformat() if conv[3] else None,
        mode=conv[4] or "normal"
    )


@router.get("/chat/conversations")
async def list_conversations(user_id: Optional[str] = None, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """List all conversations (includes mode)"""

    result = await db.execute(
        text("SELECT id, title, created_at, updated_at, mode FROM conversations ORDER BY updated_at DESC LIMIT :limit"),
        {"limit": limit}
    )

    conversations = []
    for row in result.fetchall():
        conversations.append({
            "id": str(row[0]),
            "title": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
            "updated_at": row[3].isoformat() if row[3] else None,
            "mode": row[4] or "normal"
        })

    return {"conversations": conversations, "total": len(conversations)}


@router.patch("/chat/conversations/{conversation_id}/title")
async def update_conversation_title(conversation_id: str, request: UpdateTitleRequest, db: AsyncSession = Depends(get_db)):
    """Update conversation title"""

    await db.execute(
        text("UPDATE conversations SET title = :title, updated_at = NOW() WHERE id = :conv_id"),
        {"title": request.title, "conv_id": conversation_id}
    )
    await db.commit()

    return {"status": "updated", "conversation_id": conversation_id, "title": request.title}


@router.patch("/chat/conversations/{conversation_id}/mode")
async def update_conversation_mode(conversation_id: str, request: UpdateModeRequest, db: AsyncSession = Depends(get_db)):
    """Update conversation mode — #25 AI Mode System"""

    if request.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Must be one of: {', '.join(VALID_MODES)}"
        )

    result = await db.execute(
        text("SELECT id FROM conversations WHERE id = :conv_id"),
        {"conv_id": conversation_id}
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.execute(
        text("UPDATE conversations SET mode = :mode, updated_at = NOW() WHERE id = :conv_id"),
        {"mode": request.mode, "conv_id": conversation_id}
    )
    await db.commit()

    print(f"🎯 Mode changed for {conversation_id[:8]}... → {request.mode}")

    return {
        "status": "updated",
        "conversation_id": conversation_id,
        "mode": request.mode
    }


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a conversation and all its messages"""

    context_manager.clear_conversation(conversation_id)

    await db.execute(text("DELETE FROM messages WHERE conversation_id = :conv_id"), {"conv_id": conversation_id})
    await db.execute(text("DELETE FROM conversations WHERE id = :conv_id"), {"conv_id": conversation_id})
    await db.commit()

    return {"status": "deleted", "conversation_id": conversation_id}


@router.get("/context/stats")
async def get_context_stats():
    """Get Redis context cache statistics"""
    return context_manager.get_stats()


# ============================================================================
# MODE MANAGEMENT ENDPOINT — #25
# ============================================================================

@router.get("/modes")
async def list_modes():
    """List available AI modes"""
    return {
        "modes": [
            {"id": "normal", "label": "Normal", "icon": "💬", "description": "General AI assistant"},
            {"id": "email", "label": "Email", "icon": "📧", "description": "Focused on Gmail and email management"},
            {"id": "calendar", "label": "Calendar", "icon": "📅", "description": "Focused on scheduling and calendar"},
            {"id": "code", "label": "Code", "icon": "🧑‍💻", "description": "Focused on programming and development"}
        ],
        "default": "normal"
    }


# ============================================================================
# MODEL MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/models")
async def list_models():
    """Get available models"""
    return {"models": model_router.get_available_models(), "default": model_router.default_model}


@router.post("/models/preview")
async def preview_model_selection(query: str, has_search: bool = False, has_files: bool = False):
    """Preview which model would be selected for a query"""
    return model_router.choose_model(query=query, has_search_results=has_search, has_files=has_files)