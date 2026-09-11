-- Extend the foundation model registry for immutable RF/XGBoost/LSTM bundles.
ALTER TABLE ml_models ADD COLUMN IF NOT EXISTS symbol VARCHAR(20);
ALTER TABLE ml_models ADD COLUMN IF NOT EXISTS timeframe VARCHAR(20);
ALTER TABLE ml_models ADD COLUMN IF NOT EXISTS artifact_checksum VARCHAR(64);
ALTER TABLE ml_models ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ml_models ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_prediction_bundle
    ON ml_models (symbol, timeframe) WHERE is_active;
-- Existing predictions remain the transactional record for generated forecasts.
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb;
