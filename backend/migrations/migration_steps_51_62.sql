-- ============================================================================
-- OmniAI - Database Migration: Steps 51-62
-- Run this ONCE before starting Steps 51-62
-- ============================================================================

-- ============================================================================
-- STEP 54: FULL-TEXT SEARCH ON MESSAGES
-- ============================================================================

-- Add search vector column
ALTER TABLE messages ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Populate from existing messages
UPDATE messages SET search_vector = to_tsvector('english', content)
WHERE search_vector IS NULL;

-- Create GIN index for fast search
CREATE INDEX IF NOT EXISTS idx_messages_search ON messages USING GIN(search_vector);

-- Auto-update trigger on insert/update
CREATE OR REPLACE FUNCTION messages_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS messages_search_trigger ON messages;
CREATE TRIGGER messages_search_trigger
    BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION messages_search_update();


-- ============================================================================
-- STEP 52: ADD updated_at TO MESSAGES (for edit tracking)
-- ============================================================================

ALTER TABLE messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;


-- ============================================================================
-- STEPS 56-62: AUTH SYSTEM TABLES
-- ============================================================================

-- Extend users table with auth columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- OAuth tokens table (for Google login + future Gmail/Calendar)
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- Sessions table (for tracking active login sessions)
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    device_info TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_user ON oauth_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);