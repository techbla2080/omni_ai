-- OmniAI Database Schema - Month 1 Week 3
-- Complete implementation from blueprint
-- Run this to create all core tables

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- CORE TABLES (As per blueprint)
-- ============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created ON users(created_at DESC);

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_updated ON conversations(updated_at DESC);
CREATE INDEX idx_conversations_messages ON conversations USING GIN (messages);

-- Action logs (MOAT: captures every interaction)
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

CREATE INDEX idx_action_logs_user ON action_logs(user_id);
CREATE INDEX idx_action_logs_time ON action_logs(created_at DESC);
CREATE INDEX idx_action_logs_type ON action_logs(action_type);

-- ============================================================================
-- SMART AI IDE TABLES (Week 4 prep)
-- ============================================================================

-- Capabilities registry
CREATE TABLE IF NOT EXISTS capabilities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    description TEXT,
    
    -- Requirements
    required_integrations TEXT[] DEFAULT '{}',
    required_tier VARCHAR(50) DEFAULT 'free',
    
    -- Discoverability
    difficulty_level INTEGER CHECK (difficulty_level BETWEEN 1 AND 5),
    popularity_score DECIMAL(3,2) DEFAULT 0.5,
    
    -- Examples
    example_prompts JSONB DEFAULT '[]',
    
    -- Metadata
    related_capabilities UUID[],
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_capabilities_category ON capabilities(category);
CREATE INDEX idx_capabilities_popularity ON capabilities(popularity_score DESC);

-- User capability discovery tracking
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

CREATE INDEX idx_user_cap_user ON user_capability_discovery(user_id);
CREATE INDEX idx_user_cap_capability ON user_capability_discovery(capability_id);

-- Capability examples (for A/B testing)
CREATE TABLE IF NOT EXISTS capability_examples (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    capability_id UUID REFERENCES capabilities(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    expected_outcome TEXT,
    
    variant_name VARCHAR(50) DEFAULT 'control',
    click_through_rate DECIMAL(5,4) DEFAULT 0,
    
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- WORKFLOW PATTERNS (MOAT: Pattern Detection)
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
-- USER INTEGRATIONS (For OAuth tokens)
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
-- TRIGGERS FOR AUTO-UPDATE
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_capabilities_updated_at BEFORE UPDATE ON capabilities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_patterns_updated_at BEFORE UPDATE ON workflow_patterns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE action_logs IS 'MOAT: Logs every user interaction for proprietary data';
COMMENT ON TABLE workflow_patterns IS 'MOAT: Detected user patterns for prediction';
COMMENT ON TABLE capabilities IS 'Smart AI IDE: Capability registry';
COMMENT ON TABLE user_capability_discovery IS 'MOAT: Learning investment tracking';

-- ============================================================================
-- COMPLETED
-- ============================================================================

SELECT 'Database schema created successfully!' as status;
