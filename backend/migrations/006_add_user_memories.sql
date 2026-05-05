-- ============================================================================
-- #38 Persistent User Memory
-- Cross-conversation memory: durable facts about the user that the AI
-- recalls in every chat across all modes. Pro feature (free tier capped at
-- 10 memories).
--
-- Storage scope: identity facts, preferences, ongoing context.
-- Conflict handling: newer wins, old marked status='superseded' for audit.
-- Soft delete: status='deleted' instead of DELETE so we can show users
-- "memory deletion" history if needed and recover from accidental deletes.
-- ============================================================================

-- Main memories table
CREATE TABLE IF NOT EXISTS user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- The actual memory content. Kept short and durable.
    -- Examples: "user is vegetarian", "user's daughter is named Ananya"
    content TEXT NOT NULL,
    
    -- Category helps with filtering and UI grouping.
    -- Locked to 3 categories from the locked architecture (decision #1).
    category VARCHAR(32) NOT NULL CHECK (category IN ('identity', 'preference', 'context')),
    
    -- Confidence score 0.0-1.0 from extraction.
    -- High confidence (0.8+): user said it directly ("I am vegetarian")
    -- Medium (0.5-0.8): inferred from context ("ordered paneer 3 times")
    -- Low (<0.5): weak inference; recall layer can ignore these
    confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    
    -- Lifecycle status — supports the "newer wins" conflict policy.
    --   active     = currently believed true, included in recall
    --   superseded = replaced by a newer memory; kept for audit
    --   deleted    = user explicitly deleted; not recalled, kept briefly for undo
    status VARCHAR(16) NOT NULL DEFAULT 'active' 
        CHECK (status IN ('active', 'superseded', 'deleted')),
    
    -- Provenance: which conversation produced this memory?
    -- ON DELETE SET NULL so deleting a conversation doesn't kill its memories
    -- (memories are user-scoped, not conversation-scoped).
    source_conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    
    -- If this memory replaced an older one, link to it for audit history.
    -- "User used to live in Delhi, now lives in Bombay" — we keep both.
    superseded_by UUID REFERENCES user_memories(id) ON DELETE SET NULL,
    
    -- Free-form metadata for future extension (eg. embedding vector ref,
    -- extraction model used, raw quote that triggered it).
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Soft expiry — set this for memories that should auto-fade.
    -- Most memories are NULL (never expire). We may use this for ephemeral
    -- context like "user is preparing for marathon in Sept" (expires after
    -- the date).
    expires_at TIMESTAMP DEFAULT NULL
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Primary lookup: get all active memories for a user, newest first.
-- This is the recall hot path — runs before every chat. Make it fast.
CREATE INDEX IF NOT EXISTS idx_user_memories_user_active 
    ON user_memories(user_id, status, created_at DESC) 
    WHERE status = 'active';

-- Category filtering for UI (settings panel groups by category)
CREATE INDEX IF NOT EXISTS idx_user_memories_user_category 
    ON user_memories(user_id, category) 
    WHERE status = 'active';

-- Provenance lookups (rare, but useful for debugging)
CREATE INDEX IF NOT EXISTS idx_user_memories_source_conv 
    ON user_memories(source_conversation_id) 
    WHERE source_conversation_id IS NOT NULL;

-- Cleanup query: find expired memories to mark deleted
CREATE INDEX IF NOT EXISTS idx_user_memories_expires 
    ON user_memories(expires_at) 
    WHERE expires_at IS NOT NULL AND status = 'active';

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Reuse the existing update_updated_at_column() function from earlier
-- migrations (used by users, conversations, etc.) — keep updated_at fresh.
CREATE TRIGGER update_user_memories_updated_at 
    BEFORE UPDATE ON user_memories 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- USER PREFERENCES KEYS (documentation only, no schema change)
-- ============================================================================
-- The users.preferences JSONB column gains 2 new keys for #38:
--
--   memory_collection_paused (bool)  — if true, skip memory extraction
--   memory_pro_unlocked (bool)       — overrides 10-memory free tier cap;
--                                       set true after Pro purchase (#45+)
--
-- Both default to absent (which means "false"). No migration needed for
-- these — the JSONB column already exists and #37's settings.py already
-- reads/writes preferences safely.