CREATE TABLE IF NOT EXISTS price_alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users ON DELETE CASCADE,
    asset_key VARCHAR(100) NOT NULL,
    direction VARCHAR(5) NOT NULL CHECK(direction IN ('above','below')),
    threshold NUMERIC(28,8) NOT NULL CHECK(threshold>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    triggered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS price_alerts_active ON price_alerts(asset_key) WHERE triggered_at IS NULL;
CREATE INDEX IF NOT EXISTS price_alerts_owner ON price_alerts(user_id,alert_id DESC);
