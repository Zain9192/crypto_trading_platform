-- Additive and rerunnable. Existing foundation portfolios remain legacy records.
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS mode VARCHAR(10) NOT NULL DEFAULT 'legacy';
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS initial_cash NUMERIC(28,8) NOT NULL DEFAULT 0 CHECK (initial_cash >= 0);
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS cash_balance NUMERIC(28,8) NOT NULL DEFAULT 0 CHECK (cash_balance >= 0);
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS risk_settings JSONB NOT NULL DEFAULT '{"min_investment":1,"max_investment":10000,"max_open_positions":10,"max_open_trades":10,"stop_loss_pct":5,"take_profit_pct":10}';
CREATE UNIQUE INDEX IF NOT EXISTS portfolios_one_paper_per_user ON portfolios(user_id) WHERE mode = 'paper';

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    portfolio_id BIGINT NOT NULL REFERENCES portfolios ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    quantity NUMERIC(28,8) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    cost_basis NUMERIC(28,8) NOT NULL DEFAULT 0 CHECK (cost_basis >= 0),
    realized_pnl NUMERIC(28,8) NOT NULL DEFAULT 0,
    PRIMARY KEY (portfolio_id, symbol),
    CHECK (quantity > 0 OR cost_basis = 0)
);
CREATE TABLE IF NOT EXISTS portfolio_orders (
    order_id UUID PRIMARY KEY,
    portfolio_id BIGINT NOT NULL REFERENCES portfolios ON DELETE CASCADE,
    client_order_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('buy','sell')),
    quantity NUMERIC(28,8) NOT NULL CHECK (quantity > 0),
    simulation_price NUMERIC(28,8) NOT NULL CHECK (simulation_price > 0),
    fee NUMERIC(28,8) NOT NULL CHECK (fee >= 0),
    notional NUMERIC(28,8) NOT NULL CHECK (notional > 0),
    stop_loss_price NUMERIC(28,8),
    take_profit_price NUMERIC(28,8),
    status VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','filled','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (portfolio_id, client_order_id)
);
CREATE INDEX IF NOT EXISTS portfolio_orders_pending ON portfolio_orders(portfolio_id, status);
CREATE TABLE IF NOT EXISTS portfolio_trades (
    trade_id BIGSERIAL PRIMARY KEY,
    portfolio_id BIGINT NOT NULL REFERENCES portfolios ON DELETE CASCADE,
    order_id UUID NOT NULL UNIQUE REFERENCES portfolio_orders,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('buy','sell')),
    quantity NUMERIC(28,8) NOT NULL CHECK (quantity > 0),
    price NUMERIC(28,8) NOT NULL CHECK (price > 0),
    fee NUMERIC(28,8) NOT NULL CHECK (fee >= 0),
    realized_pnl NUMERIC(28,8) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS portfolio_trades_history ON portfolio_trades(portfolio_id, trade_id DESC);
