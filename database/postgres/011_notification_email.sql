CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES users ON DELETE CASCADE,
    email_enabled BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS notification_email_outbox (
    notification_id BIGINT PRIMARY KEY REFERENCES notifications ON DELETE CASCADE,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS notification_email_due ON notification_email_outbox(next_attempt_at)
    WHERE sent_at IS NULL AND attempts<5;
CREATE OR REPLACE FUNCTION enqueue_notification_email() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO notification_email_outbox(notification_id)
    SELECT NEW.notification_id FROM notification_preferences p JOIN users u USING(user_id)
    WHERE p.user_id=NEW.user_id AND p.email_enabled AND u.is_active AND u.is_email_verified
    ON CONFLICT DO NOTHING;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS notification_email_enqueue ON notifications;
CREATE TRIGGER notification_email_enqueue AFTER INSERT ON notifications
FOR EACH ROW EXECUTE FUNCTION enqueue_notification_email();
