CREATE TABLE IF NOT EXISTS verification_email_outbox (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    token_ciphertext TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS verification_email_due ON verification_email_outbox(next_attempt_at)
    WHERE sent_at IS NULL AND attempts < 5;
