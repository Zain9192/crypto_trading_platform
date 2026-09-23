CREATE TABLE IF NOT EXISTS admin_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT NOT NULL REFERENCES users,
    target_id BIGINT NOT NULL REFERENCES users,
    action VARCHAR(40) NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS admin_audit_recent ON admin_audit(audit_id DESC);
