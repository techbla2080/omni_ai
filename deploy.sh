-- ============================================================================
-- OmniAI Production Database Schema
-- Combines original schema + auth system tables
-- Fixes column name mismatches (auth.py expects password_hash, name)
-- ============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- USERS TABLE (Fixed for auth.py compatibility)
-- auth.py uses: password_hash, name (not hashed_password, full_name)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    name VARCHAR(255),
    avatar_url TEXT,
    google_id VARCHAR(255),
    preferences JSONB DEFAULT '{}',
    reset_token TEXT,
    reset_token_expires TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);

-- ============================================================================
-- CONVERSATIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_messages ON conversations USING GIN (messages);

-- ============================================================================
-- MESSAGES TABLE (for edit/delete - Step 52)
-- ============================================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    model VARCHAR(100),
    tokens_used INTEGER,
    feedback VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

-- ============================================================================
-- SESSIONS TABLE (auth - Step 60)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    device_info TEXT,
    ip_address VARCHAR(45),
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- ============================================================================
-- OAUTH TOKENS TABLE (Google OAuth - Step 60)
-- ============================================================================
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_oauth_user ON oauth_tokens(user_id);

-- ============================================================================
-- FILES TABLE (file processing)
-- ============================================================================
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(50),
    file_size INTEGER,
    file_path TEXT,
    extracted_text TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_files_conversation ON files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type);

-- ============================================================================
-- ACTION LOGS (MOAT: captures every interaction)
-- ============================================================================
CREATE TABLE IF NOT EXISTS action_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    action_type VARCHAR(100) NOT NULL,
    context JSONB,
    tool_used VARCHAR(100),
    success BOOLEAN,
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_action_logs_user ON action_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_action_logs_time ON action_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_logs_type ON action_logs(action_type);

-- ============================================================================
-- CAPABILITIES REGISTRY (Smart AI IDE)
-- ============================================================================
CREATE TABLE IF NOT EXISTS capabilities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    description TEXT,
    required_integrations TEXT[] DEFAULT '{}',
    required_tier VARCHAR(50) DEFAULT 'free',
    difficulty_level INTEGER CHECK (difficulty_level BETWEEN 1 AND 5),
    popularity_score DECIMAL(3,2) DEFAULT 0.5,
    example_prompts JSONB DEFAULT '[]',
    related_capabilities UUID[],
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capabilities_category ON capabilities(category);

-- ============================================================================
-- USER CAPABILITY DISCOVERY
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_capability_discovery (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    capability_id UUID REFERENCES capabilities(id) ON DELETE CASCADE,
    discovered_at TIMESTAMP DEFAULT NOW(),
    discovery_method VARCHAR(50),
    first_used_at TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    bookmarked BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, capability_id)
);

-- ============================================================================
-- WORKFLOW PATTERNS
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    action_sequence JSONB[] NOT NULL,
    trigger_conditions JSONB DEFAULT '{}',
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_executed TIMESTAMP,
    automation_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- USER INTEGRATIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    integration_name VARCHAR(100) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    scopes TEXT[],
    metadata JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, integration_name)
);

-- ============================================================================
-- AUTO-UPDATE TRIGGERS
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_users_updated_at') THEN
        CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_conversations_updated_at') THEN
        CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END;
$$;

-- ============================================================================
-- FULL TEXT SEARCH INDEX (Step 54)
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_messages_content_search ON messages USING GIN (to_tsvector('english', content));

SELECT 'OmniAI database initialized successfully!' as status;