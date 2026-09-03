db = db.getSiblingDB('crypto_market');

db.createCollection('market_data');
db.market_data.createIndex(
  { symbol: 1, interval: 1, timestamp: -1 },
  { unique: true, name: 'market_data_symbol_interval_timestamp' },
);

db.createCollection('prediction_logs');
db.prediction_logs.createIndex(
  { symbol: 1, timeframe: 1, created_at: -1 },
  { name: 'prediction_logs_symbol_timeframe_created' },
);
