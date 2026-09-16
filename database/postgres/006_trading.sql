CREATE TABLE IF NOT EXISTS trading_bots (
    bot_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users ON DELETE CASCADE,
    portfolio_id BIGINT NOT NULL REFERENCES portfolios ON DELETE CASCADE,
    symbol VARCHAR(41) NOT NULL,
    config JSONB NOT NULL,
    state VARCHAR(10) NOT NULL DEFAULT 'stopped' CHECK (state IN ('stopped','running','stopping','error')),
    revision BIGINT NOT NULL DEFAULT 1,
    failures INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_result TEXT,
    last_tick_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, symbol),
    CHECK (symbol ~ '^[A-Z0-9]{1,20}/USD$'),
    CHECK (config->>'mode' = 'paper')
);
CREATE INDEX IF NOT EXISTS trading_bots_due ON trading_bots(next_run_at) WHERE state IN ('running','stopping');
CREATE TABLE IF NOT EXISTS trading_decisions (
    decision_id BIGSERIAL PRIMARY KEY,
    bot_id UUID NOT NULL REFERENCES trading_bots ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    signal VARCHAR(4) NOT NULL CHECK (signal IN ('buy','sell','hold')),
    reason TEXT NOT NULL,
    order_id UUID REFERENCES portfolio_orders,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bot_id, event_key)
);
CREATE TABLE IF NOT EXISTS trading_positions (
    bot_id UUID PRIMARY KEY REFERENCES trading_bots ON DELETE CASCADE,
    quantity NUMERIC(28,8) NOT NULL CHECK (quantity > 0),
    entry_price NUMERIC(28,8) NOT NULL CHECK (entry_price > 0),
    stop_loss_price NUMERIC(28,8),
    take_profit_price NUMERIC(28,8),
    entry_order_id UUID NOT NULL REFERENCES portfolio_orders,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS trading_worker_heartbeat (
    worker_id VARCHAR(100) PRIMARY KEY,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
