CREATE TABLE IF NOT EXISTS notifications (
    notification_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    kind VARCHAR(40) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ,
    UNIQUE(user_id, event_key)
);
CREATE INDEX IF NOT EXISTS notifications_inbox ON notifications(user_id, notification_id DESC);
CREATE INDEX IF NOT EXISTS notifications_unread ON notifications(user_id) WHERE read_at IS NULL;

CREATE OR REPLACE FUNCTION notify_paper_fill() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO notifications(user_id, event_key, kind, payload)
    SELECT user_id, 'paper-fill:' || NEW.trade_id, 'trade_executed',
        jsonb_build_object('mode','paper','order_id',NEW.order_id,'symbol',NEW.symbol,
            'side',NEW.side,'quantity',NEW.quantity::text,'price',NEW.price::text,
            'fee',NEW.fee::text,'quote_currency','USD')
    FROM portfolios WHERE portfolio_id=NEW.portfolio_id
    ON CONFLICT(user_id,event_key) DO NOTHING;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS paper_fill_notification ON portfolio_trades;
CREATE TRIGGER paper_fill_notification AFTER INSERT ON portfolio_trades
FOR EACH ROW EXECUTE FUNCTION notify_paper_fill();

CREATE OR REPLACE FUNCTION notify_sandbox_fill() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO notifications(user_id,event_key,kind,payload)
    SELECT b.user_id, 'sandbox-fill:' || NEW.connection_id || ':' || NEW.symbol || ':' || NEW.trade_id,
        'trade_executed', jsonb_build_object('mode','sandbox','bot_id',b.bot_id,
            'order_id',NEW.order_id,'symbol',NEW.symbol,'side',o.side,
            'quantity',NEW.quantity::text,'price',NEW.price::text,'fee',NEW.fee::text,
            'fee_currency',NEW.fee_currency,'quote_currency','USDT','executed_at',NEW.executed_at)
    FROM sandbox_orders o JOIN trading_bots b USING(bot_id) WHERE o.order_id=NEW.order_id
    ON CONFLICT(user_id,event_key) DO NOTHING;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sandbox_fill_notification ON sandbox_fills;
CREATE TRIGGER sandbox_fill_notification AFTER INSERT ON sandbox_fills
FOR EACH ROW EXECUTE FUNCTION notify_sandbox_fill();
