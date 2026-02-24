-- Add feedback table for response quality tracking

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)), -- -1 = thumbs down, 1 = thumbs up
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Ensure one feedback per message
    UNIQUE(message_id)
);

-- Index for querying feedback
CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_conversation ON feedback(conversation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);

-- Add feedback statistics view
CREATE OR REPLACE VIEW feedback_stats AS
SELECT 
    COUNT(*) FILTER (WHERE rating = 1) as thumbs_up,
    COUNT(*) FILTER (WHERE rating = -1) as thumbs_down,
    COUNT(*) as total_feedback,
    ROUND(100.0 * COUNT(*) FILTER (WHERE rating = 1) / NULLIF(COUNT(*), 0), 2) as satisfaction_rate
FROM feedback;