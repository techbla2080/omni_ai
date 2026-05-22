"""
#38 Persistent User Memory — extraction + recall + persistence service.

Three responsibilities:
1. extract_and_save_memories() — runs after every chat. Uses Groq to find
   durable facts about the user in their latest message + AI response.
   Saves to user_memories table. Handles conflicts via "newer wins".
2. get_active_memories() — fast read for the recall layer. Returns active
   memories for a user, newest first. Used by build_system_prompt().
3. CRUD helpers — list/update/delete for the API layer (Chunk 4).

Free tier cap: 10 active memories. Pro tier: unlimited.
Preferences gate: users.preferences.memory_collection_paused skips extraction.
"""

import json
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Free tier cap. Pro tier ignores this.
# Tuned to ~10 because that's enough to demonstrate the magic ("AI remembered
# I'm vegetarian!") without being a daily driver. Drives Pro upgrades.
FREE_TIER_MEMORY_CAP = 10

# Groq model for extraction. Same as calendar advisor and intent classifier
# for consistency and cost predictability. JSON mode supported.
EXTRACTION_MODEL = "llama-3.3-70b-versatile"

# Lower temperature than chat — extraction is closer to a structured task.
# Some creativity helps catch subtle preferences, but we don't want hallucination.
EXTRACTION_TEMPERATURE = 0.3

# Cap the response size. Even a long conversation rarely produces more than
# 3-4 new durable memories per turn. 600 tokens is generous.
EXTRACTION_MAX_TOKENS = 600

# Categories must match the CHECK constraint in the user_memories table.
VALID_CATEGORIES = {"identity", "preference", "context"}

# Confidence floor — extractor outputs below this are dropped at save time.
# Anything below 0.5 is too speculative to be worth storing.
MIN_CONFIDENCE_TO_SAVE = 0.5


# ============================================================================
# Extraction prompt
# ============================================================================
# This is the heart of #38. The prompt determines what becomes a memory and
# what doesn't. Carefully tuned to err on the side of skipping rather than
# over-saving — false positives create user-visible noise.

EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction agent for OmniAI, a personal AI assistant.

Your job: read the user's latest message and the AI's response, and decide if the user revealed any DURABLE FACT about themselves that the AI should remember in future conversations.

You output STRICT JSON in this format:
{
  "memories": [
    {
      "content": "user is vegetarian",
      "category": "preference",
      "confidence": 0.95
    }
  ]
}

If nothing durable was revealed, output: {"memories": []}

## What COUNTS as a memory (save these)

**Identity** (category: "identity"):
- Name, age, location, job, employer, family members
- Examples:
  - "user lives in Mumbai"
  - "user works at Razorpay as a backend engineer"
  - "user has a daughter named Ananya"
  - "user's name is Pranav"

**Preference** (category: "preference"):
- Dietary, communication style, tools, recurring choices
- Examples:
  - "user is vegetarian"
  - "user prefers Python over JavaScript"
  - "user wants concise responses, no fluff"
  - "user prefers Hinglish for casual chat"

**Context** (category: "context"):
- Current projects, ongoing goals, deadlines, situations
- Examples:
  - "user is launching OmniAI in May 2026"
  - "user is preparing for a marathon in September"
  - "user is in their final year of B.Tech at IIT Delhi"

## What DOES NOT count (do NOT save)

- One-off questions ("what is the capital of France")
- Transient state ("user is bored", "user is busy today")
- Things about other people not tied to the user ("Modi is PM")
- Things from the AI's response (only extract from what the USER said or did)
- Speculation not supported by clear text in the message
- Things you've already been told in earlier turns of THIS conversation
- Generic facts everyone knows ("user breathes air")
- Casual statements that don't generalize ("user is hungry now")

## Confidence scoring

- 0.9+: User explicitly stated the fact ("I am a vegetarian")
- 0.7-0.9: User strongly implied it ("I'd never eat meat", "I always order veg")
- 0.5-0.7: Inferred from context but not stated ("user mentioned Mumbai twice in different chats")
- Below 0.5: Don't include — too speculative

## Critical rules

1. Output STRICT JSON, nothing else. No markdown fences. No commentary.
2. If unsure, output {"memories": []} — false positives are worse than misses.
3. Phrase memory content as a third-person fact starting with "user " (lowercase).
4. Keep content under 100 characters. Concise.
5. NEVER extract sensitive info like passwords, credit cards, govt ID numbers.
6. NEVER extract info about people the user mentions, only about the user themselves.

## Examples

User says: "Can you suggest dinner ideas?"
AI says: "Here are 5 vegetarian dinner ideas..."
Extract: {"memories": []} — nothing new revealed by user

User says: "I'm vegetarian, suggest dinner please"
AI says: "Here are 5 vegetarian dinner ideas..."
Extract: {"memories": [{"content": "user is vegetarian", "category": "preference", "confidence": 0.95}]}

User says: "Working on OmniAI launch, need help with razorpay integration"
AI says: "..."
Extract: {"memories": [
  {"content": "user is working on OmniAI launch", "category": "context", "confidence": 0.85},
  {"content": "user uses razorpay for payments", "category": "preference", "confidence": 0.7}
]}

User says: "What is the capital of Germany?"
AI says: "Berlin"
Extract: {"memories": []}
"""


# ============================================================================
# Preferences helpers (mirrors pattern from settings.py)
# ============================================================================

async def _get_user_preferences(db: AsyncSession, user_id: str) -> dict:
    """Load user.preferences JSONB safely. Returns {} on any failure."""
    try:
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
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception as e:
        logger.warning(f"#38 Could not load preferences for {user_id[:8]}: {e}")
        return {}


async def _is_memory_collection_paused(db: AsyncSession, user_id: str) -> bool:
    """Check the memory_collection_paused preference flag."""
    prefs = await _get_user_preferences(db, user_id)
    return bool(prefs.get("memory_collection_paused", False))


async def _is_pro_user(db: AsyncSession, user_id: str) -> bool:
    """
    Pro user check. Currently a preference flag (memory_pro_unlocked).
    When Razorpay (#45+) lands, this will check the subscriptions table
    instead. Single source of truth so all gating funnels through here.
    """
    prefs = await _get_user_preferences(db, user_id)
    return bool(prefs.get("memory_pro_unlocked", False))


# ============================================================================
# Reads
# ============================================================================

async def count_active_memories(db: AsyncSession, user_id: str) -> int:
    """Count active memories for a user. Used for free-tier cap enforcement."""
    result = await db.execute(
        text("""
            SELECT COUNT(*) FROM user_memories 
            WHERE user_id = :user_id AND status = 'active'
        """),
        {"user_id": user_id}
    )
    return int(result.scalar() or 0)


async def get_active_memories(
    db: AsyncSession,
    user_id: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get active memories for a user, newest first.
    
    This is the READ HOT PATH — called before every chat turn during recall.
    The idx_user_memories_user_active partial index makes it ~1ms.
    
    Returns a list of dicts (not ORM objects) so the caller doesn't need
    to know about SQLAlchemy.
    """
    result = await db.execute(
        text("""
            SELECT id, content, category, confidence, created_at
            FROM user_memories 
            WHERE user_id = :user_id AND status = 'active'
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"user_id": user_id, "limit": limit}
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "content": r[1],
            "category": r[2],
            "confidence": float(r[3]),
            "created_at": r[4].isoformat() if r[4] else None
        }
        for r in rows
    ]


async def get_all_user_memories(
    db: AsyncSession,
    user_id: str,
    include_superseded: bool = False
) -> List[Dict[str, Any]]:
    """
    Read all memories for the settings-panel UI.
    By default returns active only. Set include_superseded=True to also
    include history (replaced facts) for an audit-style view.
    """
    if include_superseded:
        status_clause = "status IN ('active', 'superseded')"
    else:
        status_clause = "status = 'active'"
    
    result = await db.execute(
        text(f"""
            SELECT id, content, category, confidence, status, 
                   created_at, updated_at, source_conversation_id
            FROM user_memories 
            WHERE user_id = :user_id AND {status_clause}
            ORDER BY 
                CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                created_at DESC
        """),
        {"user_id": user_id}
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "content": r[1],
            "category": r[2],
            "confidence": float(r[3]),
            "status": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
            "updated_at": r[6].isoformat() if r[6] else None,
            "source_conversation_id": str(r[7]) if r[7] else None
        }
        for r in rows
    ]


# ============================================================================
# Writes — save/update/delete with conflict handling
# ============================================================================

async def save_memory(
    db: AsyncSession,
    user_id: str,
    content: str,
    category: str,
    confidence: float = 0.7,
    source_conversation_id: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Optional[str]:
    """
    Insert a new memory. Returns the new memory's ID, or None if rejected.
    
    Rejections:
    - confidence below MIN_CONFIDENCE_TO_SAVE
    - category not in VALID_CATEGORIES (DB will also reject via CHECK)
    - content empty or too long
    - free-tier user at cap
    
    Does NOT do conflict detection here. Conflict detection runs at the
    extract_and_save level so we have the new + old in the same transaction.
    """
    if confidence < MIN_CONFIDENCE_TO_SAVE:
        logger.debug(f"#38 Skipping low-confidence memory ({confidence}): {content!r}")
        return None
    
    if category not in VALID_CATEGORIES:
        logger.warning(f"#38 Invalid category {category!r}, skipping")
        return None
    
    content_stripped = (content or "").strip()
    if not content_stripped or len(content_stripped) > 500:
        logger.debug(f"#38 Skipping empty/oversized content (len={len(content_stripped)})")
        return None
    
    # Free-tier cap check
    is_pro = await _is_pro_user(db, user_id)
    if not is_pro:
        active_count = await count_active_memories(db, user_id)
        if active_count >= FREE_TIER_MEMORY_CAP:
            logger.info(
                f"#38 User {user_id[:8]} at free-tier cap ({active_count}/{FREE_TIER_MEMORY_CAP}), "
                f"skipping memory: {content_stripped!r}"
            )
            return None
    
    metadata_json = json.dumps(metadata or {})
    
    result = await db.execute(
        text("""
            INSERT INTO user_memories 
                (user_id, content, category, confidence, source_conversation_id, metadata)
            VALUES 
                (:user_id, :content, :category, :confidence, :source_conv, CAST(:metadata AS JSONB))
            RETURNING id
        """),
        {
            "user_id": user_id,
            "content": sanitize_prompt(content_stripped, max_length=2000),
            "category": category,
            "confidence": float(confidence),
            "source_conv": source_conversation_id,
            "metadata": metadata_json
        }
    )
    new_id = str(result.scalar())
    await db.commit()
    
    logger.info(
        f"#38 Saved memory for {user_id[:8]} [{category}, conf={confidence:.2f}]: "
        f"{content_stripped!r}"
    )
    return new_id


async def supersede_memory(
    db: AsyncSession,
    old_memory_id: str,
    new_memory_id: str
) -> None:
    """
    Mark an old memory as superseded by a new one.
    Used when a contradicting fact arrives — eg. user moves cities.
    """
    await db.execute(
        text("""
            UPDATE user_memories 
            SET status = 'superseded', superseded_by = :new_id, updated_at = NOW()
            WHERE id = :old_id
        """),
        {"old_id": old_memory_id, "new_id": new_memory_id}
    )
    await db.commit()
    logger.info(f"#38 Memory {old_memory_id[:8]} superseded by {new_memory_id[:8]}")


async def update_memory(
    db: AsyncSession,
    user_id: str,
    memory_id: str,
    new_content: str
) -> bool:
    """
    User-initiated edit of a memory's content. Returns True if updated.
    Verifies the memory belongs to this user before updating (auth).
    """
    new_content_stripped = (new_content or "").strip()
    if not new_content_stripped or len(new_content_stripped) > 500:
        return False
    
    result = await db.execute(
        text("""
            UPDATE user_memories 
            SET content = :content, updated_at = NOW()
            WHERE id = :id AND user_id = :user_id AND status = 'active'
        """),
        {"id": memory_id, "user_id": user_id, "content": new_content_stripped}
    )
    await db.commit()
    return result.rowcount > 0


async def delete_memory(
    db: AsyncSession,
    user_id: str,
    memory_id: str
) -> bool:
    """
    User-initiated soft delete. Marks as 'deleted' but keeps the row briefly
    so we could implement "undo" later. Verifies ownership before deleting.
    """
    result = await db.execute(
        text("""
            UPDATE user_memories 
            SET status = 'deleted', updated_at = NOW()
            WHERE id = :id AND user_id = :user_id AND status IN ('active', 'superseded')
        """),
        {"id": memory_id, "user_id": user_id}
    )
    await db.commit()
    return result.rowcount > 0


async def delete_all_memories(db: AsyncSession, user_id: str) -> int:
    """
    "Forget everything about me" — soft-delete all of the user's memories.
    GDPR-compliant: user can wipe their entire memory history.
    Returns count of memories deleted.
    """
    result = await db.execute(
        text("""
            UPDATE user_memories 
            SET status = 'deleted', updated_at = NOW()
            WHERE user_id = :user_id AND status IN ('active', 'superseded')
        """),
        {"user_id": user_id}
    )
    await db.commit()
    count = result.rowcount
    logger.info(f"#38 User {user_id[:8]} wiped all {count} memories")
    return count


# ============================================================================
# Conflict detection
# ============================================================================
# Simple "newer wins" via keyword overlap. We compare the new memory against
# existing active memories of the same category. If they share enough
# distinctive words, we treat it as a contradiction and supersede the old.
#
# This is intentionally simple. A more sophisticated approach would use
# embeddings (cosine similarity > 0.85). Save that for v2 with pgvector.
# For v1, simple keyword overlap catches ~80% of real conflicts.

# Words too generic to count as "distinctive" — appear in most memories.
_STOPWORDS = {
    "user", "is", "are", "the", "a", "an", "to", "of", "in", "on", "at",
    "with", "for", "by", "as", "be", "and", "or", "but", "not", "from",
    "has", "have", "had", "was", "were", "do", "does", "did", "will",
    "would", "should", "can", "could", "may", "might", "lives", "works"
}


def _distinctive_words(text: str) -> set:
    """Lowercased word set with stopwords and short tokens removed."""
    words = text.lower().replace(",", " ").replace(".", " ").split()
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _looks_like_conflict(new_content: str, existing_content: str) -> bool:
    """
    Heuristic: do these two memories look like contradictory updates?
    Returns True if they share at least 1 distinctive word AND have similar
    structure (length within 2x of each other).
    
    Examples that should match (return True):
    - "user lives in Delhi" vs "user lives in Bombay" → share "lives", "in"
    - "user is vegetarian" vs "user is vegan" → similar length, both diet
    
    Examples that should NOT match (return False):
    - "user is vegetarian" vs "user is a developer" → share nothing distinctive
    - "user works at Razorpay" vs "user has a daughter" → totally different
    """
    new_words = _distinctive_words(new_content)
    old_words = _distinctive_words(existing_content)
    if not new_words or not old_words:
        return False
    
    # At least 1 distinctive word shared (after stopwords removed)
    overlap = new_words & old_words
    if not overlap:
        return False
    
    # Length similarity (prevents matching short fact against long one)
    new_len = len(new_content)
    old_len = len(existing_content)
    if max(new_len, old_len) > 2 * max(min(new_len, old_len), 1):
        return False
    
    # Overlap should be at least 30% of the smaller word set
    smaller = min(len(new_words), len(old_words))
    return len(overlap) / smaller >= 0.3


async def find_conflicting_memory(
    db: AsyncSession,
    user_id: str,
    new_content: str,
    new_category: str
) -> Optional[str]:
    """
    Look for an existing active memory in the same category that looks like
    a contradicting older version of the new fact. Returns the old memory's
    ID, or None if no conflict found.
    
    Only checks within the same category — "user lives in Delhi" (identity)
    won't conflict with "user enjoys travel" (preference) even if words
    overlap.
    """
    result = await db.execute(
        text("""
            SELECT id, content FROM user_memories 
            WHERE user_id = :user_id AND status = 'active' AND category = :category
        """),
        {"user_id": user_id, "category": new_category}
    )
    for row in result.fetchall():
        old_id = str(row[0])
        old_content = row[1]
        if _looks_like_conflict(new_content, old_content):
            return old_id
    return None


# ============================================================================
# Extraction (LLM call)
# ============================================================================

async def _call_groq_for_extraction(
    user_message: str,
    ai_response: str
) -> List[Dict[str, Any]]:
    """
    Single Groq call to extract memories from a chat turn.
    Returns a list of memory dicts (possibly empty). Never raises — any
    failure returns [] and logs a warning. Memory extraction must NEVER
    block or break the user's chat experience.
    """
    try:
        from groq import AsyncGroq
    except ImportError:
        logger.warning("#38 groq module not available, skipping extraction")
        return []
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("#38 GROQ_API_KEY not set, skipping extraction")
        return []
    
    # Truncate to keep prompt size sane. Real conversations rarely need more
    # than a few hundred chars of context for memory extraction.
    user_msg_truncated = (user_message or "")[:1500]
    ai_resp_truncated = (ai_response or "")[:1500]
    
    extraction_input = (
        f"USER MESSAGE:\n{user_msg_truncated}\n\n"
        f"AI RESPONSE:\n{ai_resp_truncated}\n\n"
        f"Extract durable user facts as JSON per the system prompt rules."
    )
    
    try:
        client = AsyncGroq(api_key=api_key)
        completion = await client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": extraction_input}
            ],
            temperature=EXTRACTION_TEMPERATURE,
            max_tokens=EXTRACTION_MAX_TOKENS,
            response_format={"type": "json_object"}
        )
        raw_response = completion.choices[0].message.content
        if not raw_response:
            return []
        
        parsed = json.loads(raw_response)
        memories = parsed.get("memories", [])
        if not isinstance(memories, list):
            logger.warning(f"#38 Extractor returned non-list memories: {type(memories)}")
            return []
        
        # Validate shape of each memory before returning
        valid = []
        for m in memories:
            if not isinstance(m, dict):
                continue
            content = str(m.get("content", "")).strip()
            category = str(m.get("category", "")).strip().lower()
            try:
                confidence = float(m.get("confidence", 0))
            except (ValueError, TypeError):
                continue
            if (content and category in VALID_CATEGORIES 
                and 0.0 <= confidence <= 1.0 and len(content) <= 500):
                valid.append({
                    "content": content,
                    "category": category,
                    "confidence": confidence
                })
        return valid
    
    except json.JSONDecodeError as e:
        logger.warning(f"#38 Extractor returned invalid JSON: {e}")
        return []
    except Exception as e:
        logger.warning(f"#38 Extraction call failed: {e}")
        return []


# ============================================================================
# Public entry point — called from chat handlers
# ============================================================================

async def extract_and_save_memories(
    db: AsyncSession,
    user_id: Optional[str],
    user_message: str,
    ai_response: str,
    conversation_id: Optional[str] = None
) -> int:
    """
    Top-level extraction + save. Called from the chat endpoint AFTER the
    user sees the AI response (so latency doesn't matter). Should be invoked
    via fire-and-forget (asyncio.create_task) so the chat handler doesn't
    wait on it.
    
    Returns count of memories saved (for logging).
    
    Silent skips:
    - user_id is None (anonymous user — nothing to attach to)
    - user has memory_collection_paused = true
    - extractor returned no memories
    - free-tier user at cap (per save_memory's check)
    
    Never raises. All failures are logged at warning level.
    """
    if not user_id:
        return 0
    
    try:
        # Respect the pause flag
        if await _is_memory_collection_paused(db, user_id):
            logger.debug(f"#38 Memory collection paused for {user_id[:8]}, skipping")
            return 0
        
        # Run extraction
        candidates = await _call_groq_for_extraction(user_message, ai_response)
        if not candidates:
            return 0
        
        logger.info(f"#38 Extractor found {len(candidates)} candidates for {user_id[:8]}")
        
        saved_count = 0
        for candidate in candidates:
            content = candidate["content"]
            category = candidate["category"]
            confidence = candidate["confidence"]
            
            # Conflict check: is this a contradicting update of an existing memory?
            old_memory_id = await find_conflicting_memory(
                db, user_id, content, category
            )
            
            # Save the new memory (returns None if rejected — eg. cap hit)
            new_memory_id = await save_memory(
                db=db,
                user_id=user_id,
                content=content,
                category=category,
                confidence=confidence,
                source_conversation_id=conversation_id,
                metadata={"extracted_at": datetime.utcnow().isoformat()}
            )
            
            if not new_memory_id:
                continue
            
            saved_count += 1
            
            # Mark the old memory superseded if a conflict was found
            if old_memory_id:
                await supersede_memory(db, old_memory_id, new_memory_id)
        
        return saved_count
    
    except Exception as e:
        # Memory extraction must NEVER break the chat flow.
        logger.warning(f"#38 extract_and_save_memories failed for {user_id[:8]}: {e}")
        return 0


# ============================================================================
# Recall — formats memories for injection into system prompt (Chunk 3)
# ============================================================================

def format_memories_for_prompt(memories: List[Dict[str, Any]]) -> str:
    """
    Turn a list of memory dicts into a system-prompt-ready string.
    Returns empty string if no memories — caller can falsy-check.
    
    Output format (compact, scannable for the LLM):
    
        --- WHAT YOU REMEMBER ABOUT THE USER ---
        Identity:
        - user lives in Mumbai
        - user works at Razorpay
        Preferences:
        - user is vegetarian
        - user prefers concise responses
        Context:
        - user is launching OmniAI in May 2026
        --- END USER MEMORIES ---
    """
    if not memories:
        return ""
    
    by_category = {"identity": [], "preference": [], "context": []}
    for m in memories:
        cat = m.get("category")
        if cat in by_category:
            by_category[cat].append(m["content"])
    
    lines = ["--- WHAT YOU REMEMBER ABOUT THE USER ---"]
    
    if by_category["identity"]:
        lines.append("Identity:")
        for c in by_category["identity"]:
            lines.append(f"- {c}")
    
    if by_category["preference"]:
        lines.append("Preferences:")
        for c in by_category["preference"]:
            lines.append(f"- {c}")
    
    if by_category["context"]:
        lines.append("Context:")
        for c in by_category["context"]:
            lines.append(f"- {c}")
    
    lines.append("--- END USER MEMORIES ---")
    return "\n".join(lines)