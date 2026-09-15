CREATE TABLE IF NOT EXISTS exchange_connections (
    connection_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    exchange VARCHAR(16) NOT NULL CHECK (exchange IN ('binance','coinbase','kraken')),
    label VARCHAR(80) NOT NULL,
    sandbox BOOLEAN NOT NULL DEFAULT TRUE,
    read_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (read_only),
    credentials_ciphertext TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, exchange, sandbox),
    CHECK (NOT sandbox OR exchange = 'binance')
);
CREATE INDEX IF NOT EXISTS exchange_connections_owner ON exchange_connections(user_id);
