-- Files table for tracking uploaded documents

CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    mime_type VARCHAR(100),
    extracted_text TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processing_error TEXT
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_files_conversation ON files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type);

-- View for file statistics
CREATE OR REPLACE VIEW file_stats AS
SELECT 
    COUNT(*) as total_files,
    COUNT(*) FILTER (WHERE processed = true) as processed_files,
    COUNT(*) FILTER (WHERE processed = false) as pending_files,
    SUM(file_size) as total_size_bytes,
    COUNT(DISTINCT conversation_id) as conversations_with_files
FROM files;