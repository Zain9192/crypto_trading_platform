CREATE TABLE IF NOT EXISTS users (
    user_id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'trader',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    total_value NUMERIC(24, 8) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crypto_assets (
    asset_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    current_price NUMERIC(24, 8),
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS trade_orders (
    order_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    asset_id BIGINT NOT NULL REFERENCES crypto_assets(asset_id),
    order_type VARCHAR(10) NOT NULL CHECK (order_type IN ('buy', 'sell')),
    amount NUMERIC(24, 8) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ml_models (
    model_id BIGSERIAL PRIMARY KEY,
    algorithm VARCHAR(50) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(50),
    metric_value DOUBLE PRECISION,
    trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (algorithm, model_version)
);

CREATE TABLE IF NOT EXISTS predictions (
    pred_id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES crypto_assets(asset_id),
    model_id BIGINT REFERENCES ml_models(model_id),
    timeframe VARCHAR(20) NOT NULL,
    predicted_price NUMERIC(24, 8),
    confidence DOUBLE PRECISION CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES crypto_assets(asset_id),
    condition VARCHAR(50) NOT NULL,
    threshold NUMERIC(24, 8) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_orders_user_created
    ON trade_orders(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_asset_timeframe_created
    ON predictions(asset_id, timeframe, created_at DESC);
