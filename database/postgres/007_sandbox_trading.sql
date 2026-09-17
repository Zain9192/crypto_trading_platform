ALTER TABLE trading_bots ALTER COLUMN portfolio_id DROP NOT NULL;
ALTER TABLE trading_bots ADD COLUMN IF NOT EXISTS connection_id UUID REFERENCES exchange_connections ON DELETE RESTRICT;
ALTER TABLE trading_bots ADD COLUMN IF NOT EXISTS close_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE trading_bots DROP CONSTRAINT IF EXISTS trading_bots_symbol_check;
ALTER TABLE trading_bots DROP CONSTRAINT IF EXISTS trading_bots_config_check;
ALTER TABLE trading_bots DROP CONSTRAINT IF EXISTS trading_bots_environment_check;
ALTER TABLE trading_bots ADD CONSTRAINT trading_bots_environment_check CHECK (
    (config->>'mode' = 'paper' AND portfolio_id IS NOT NULL AND connection_id IS NULL AND symbol ~ '^[A-Z0-9]{1,20}/USD$') OR
    (config->>'mode' = 'sandbox' AND portfolio_id IS NULL AND connection_id IS NOT NULL AND symbol ~ '^[A-Z0-9]{1,20}/USDT$')
);
CREATE UNIQUE INDEX IF NOT EXISTS trading_bots_connection_symbol ON trading_bots(connection_id,symbol) WHERE connection_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS sandbox_orders (
    order_id UUID PRIMARY KEY,
    bot_id UUID NOT NULL REFERENCES trading_bots ON DELETE RESTRICT,
    connection_id UUID NOT NULL REFERENCES exchange_connections ON DELETE RESTRICT,
    event_key TEXT NOT NULL,
    symbol VARCHAR(41) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('buy','sell')),
    amount NUMERIC(38,18) NOT NULL CHECK (amount>0),
    limit_price NUMERIC(38,18) NOT NULL CHECK (limit_price>0),
    status VARCHAR(20) NOT NULL DEFAULT 'submitting' CHECK (status IN ('submitting','unknown','open','partially_filled','filled','cancelled','rejected','expired')),
    exchange_order_id TEXT,
    filled NUMERIC(38,18) NOT NULL DEFAULT 0,
    cost NUMERIC(38,18) NOT NULL DEFAULT 0,
    cancel_requested BOOLEAN NOT NULL DEFAULT false,
    last_error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_reconcile_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(bot_id,event_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS sandbox_one_unresolved_order ON sandbox_orders(connection_id)
    WHERE status IN ('submitting','unknown','open','partially_filled');
CREATE TABLE IF NOT EXISTS sandbox_positions (
    bot_id UUID PRIMARY KEY REFERENCES trading_bots ON DELETE RESTRICT,
    quantity NUMERIC(38,18) NOT NULL DEFAULT 0 CHECK (quantity>=0),
    cost_basis NUMERIC(38,18) NOT NULL DEFAULT 0 CHECK (cost_basis>=0),
    realized_pnl NUMERIC(38,18) NOT NULL DEFAULT 0,
    entry_order_id UUID REFERENCES sandbox_orders,
    stop_loss_price NUMERIC(38,18),
    take_profit_price NUMERIC(38,18),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sandbox_fills (
    connection_id UUID NOT NULL REFERENCES exchange_connections ON DELETE RESTRICT,
    symbol VARCHAR(41) NOT NULL,
    trade_id TEXT NOT NULL,
    order_id UUID NOT NULL REFERENCES sandbox_orders ON DELETE RESTRICT,
    quantity NUMERIC(38,18) NOT NULL CHECK(quantity>0),
    price NUMERIC(38,18) NOT NULL CHECK(price>0),
    cost NUMERIC(38,18) NOT NULL CHECK(cost>0),
    fee NUMERIC(38,18) NOT NULL CHECK(fee>=0),
    fee_currency VARCHAR(30) NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(connection_id,symbol,trade_id)
);
CREATE TABLE IF NOT EXISTS sandbox_balances (
    connection_id UUID NOT NULL REFERENCES exchange_connections ON DELETE RESTRICT,
    currency VARCHAR(30) NOT NULL,
    free NUMERIC(38,18) NOT NULL,
    used NUMERIC(38,18) NOT NULL,
    total NUMERIC(38,18) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(connection_id,currency)
);

ALTER TABLE trading_bots ADD COLUMN IF NOT EXISTS last_price NUMERIC(38,18);
ALTER TABLE trading_bots ADD COLUMN IF NOT EXISTS price_observed_at TIMESTAMPTZ;
