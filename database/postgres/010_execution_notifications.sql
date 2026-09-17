CREATE OR REPLACE FUNCTION notify_paper_exit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.reason IN ('stop_loss','take_profit') AND NEW.order_id IS NOT NULL THEN
        INSERT INTO notifications(user_id,event_key,kind,payload)
        SELECT b.user_id,'paper-exit:' || NEW.decision_id,NEW.reason,
            jsonb_build_object('mode','paper','bot_id',b.bot_id,'symbol',b.symbol,
                'order_id',NEW.order_id,'quantity',t.quantity::text,'price',t.price::text,'quote_currency','USD')
        FROM trading_bots b JOIN portfolio_trades t ON t.order_id=NEW.order_id
        WHERE b.bot_id=NEW.bot_id ON CONFLICT(user_id,event_key) DO NOTHING;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS paper_exit_notification ON trading_decisions;
CREATE TRIGGER paper_exit_notification AFTER INSERT ON trading_decisions
FOR EACH ROW EXECUTE FUNCTION notify_paper_exit();

CREATE OR REPLACE FUNCTION notify_sandbox_exit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO notifications(user_id,event_key,kind,payload)
    SELECT b.user_id,'sandbox-exit:' || NEW.connection_id || ':' || NEW.symbol || ':' || NEW.trade_id,d.reason,
        jsonb_build_object('mode','sandbox','bot_id',b.bot_id,'symbol',NEW.symbol,
            'order_id',NEW.order_id,'quantity',NEW.quantity::text,'price',NEW.price::text,'quote_currency','USDT')
    FROM sandbox_orders o JOIN trading_bots b USING(bot_id)
        JOIN trading_decisions d ON d.bot_id=o.bot_id AND d.event_key=o.event_key
    WHERE o.order_id=NEW.order_id AND d.reason IN ('stop_loss','take_profit')
    ON CONFLICT(user_id,event_key) DO NOTHING;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sandbox_exit_notification ON sandbox_fills;
CREATE TRIGGER sandbox_exit_notification AFTER INSERT ON sandbox_fills
FOR EACH ROW EXECUTE FUNCTION notify_sandbox_exit();

CREATE OR REPLACE FUNCTION notify_bot_failure() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.failures=0 AND NEW.failures>0) OR (NEW.state='error' AND OLD.state<>'error') THEN
        INSERT INTO notifications(user_id,event_key,kind,payload)
        VALUES (NEW.user_id,'bot-failure:' || NEW.bot_id || ':' || nextval('notifications_notification_id_seq'),
            'bot_failure',jsonb_build_object('mode',NEW.config->>'mode','bot_id',NEW.bot_id,
                'symbol',NEW.symbol,'state',NEW.state,'failures',NEW.failures,
                'message',CASE WHEN NEW.state='error' THEN 'Bot paused after repeated execution failures. Review the bot before restarting.'
                    ELSE 'Bot execution failed. Automatic retry is scheduled.' END));
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS bot_failure_notification ON trading_bots;
CREATE TRIGGER bot_failure_notification AFTER UPDATE ON trading_bots
FOR EACH ROW EXECUTE FUNCTION notify_bot_failure();

CREATE OR REPLACE FUNCTION notify_exchange_failure() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IN ('unknown','rejected') AND NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO notifications(user_id,event_key,kind,payload)
        SELECT user_id,'exchange-failure:' || NEW.order_id || ':' || NEW.status,'exchange_failure',
            jsonb_build_object('mode','sandbox','bot_id',NEW.bot_id,'symbol',NEW.symbol,
                'order_id',NEW.order_id,'status',NEW.status,
                'message',CASE WHEN NEW.status='unknown' THEN 'Order outcome is unresolved. Reconciliation continues; submission will not be repeated.'
                    ELSE 'Exchange rejected the order.' END)
        FROM trading_bots WHERE bot_id=NEW.bot_id ON CONFLICT(user_id,event_key) DO NOTHING;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS exchange_failure_notification ON sandbox_orders;
CREATE TRIGGER exchange_failure_notification AFTER UPDATE ON sandbox_orders
FOR EACH ROW EXECUTE FUNCTION notify_exchange_failure();
