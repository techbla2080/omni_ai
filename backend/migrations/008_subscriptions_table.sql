-- ============================================================================
-- Migration #43 — Subscriptions table (paired with #42 webhook handler)
-- ============================================================================
--
-- Records active Pro subscriptions. Created when payment.captured webhook
-- fires (or when /payments/verify is called optimistically).
--
-- "Is user Pro?" logic: latest row where is_active = TRUE AND expires_at > NOW()
--
-- To apply on server:
--   docker compose exec -T postgres psql -U omniai -d omniai \
--     < backend/migrations/008_subscriptions_table.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Plan + linkage to the payment that bought it
    plan VARCHAR(50) NOT NULL,                                    -- 'pro_monthly'
    payment_id UUID REFERENCES payments(id),
    razorpay_order_id   VARCHAR(255),
    razorpay_payment_id VARCHAR(255) UNIQUE,                      -- one sub per Razorpay payment

    -- Lifecycle
    started_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    auto_renew   BOOLEAN NOT NULL DEFAULT FALSE,                  -- for future

    -- Audit
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id    ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_at ON subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_subscriptions_active_lookup
    ON subscriptions(user_id, is_active, expires_at)
    WHERE is_active = TRUE;

-- Webhook idempotency table — record every event we've processed so duplicate
-- webhook deliveries don't double-activate subscriptions
CREATE TABLE IF NOT EXISTS webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider VARCHAR(50) NOT NULL,                                -- 'razorpay'
    event_id VARCHAR(255) NOT NULL,                               -- razorpay event id
    event_type VARCHAR(100) NOT NULL,                             -- 'payment.captured' etc
    payload JSONB,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(provider, event_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_provider_type
    ON webhook_events(provider, event_type);

SELECT 'subscriptions + webhook_events tables ready' AS status;