# Phase 4 — AI/ML Prediction

Branch: `feature/ai-prediction`, based on main after Phase 3 PR #6 was merged.

- [x] Confirm Phase 3 merge and passing CI.
- [x] Load and validate stored, closed OHLCV candles.
- [x] Engineer causal returns, volatility, volume and technical-indicator features.
- [x] Split train/validation/test chronologically with purged label boundaries; fit preprocessing on train only.
- [x] Train Random Forest direction classifier.
- [x] Train XGBoost next-return regressor and convert forecasts to prices.
- [x] Train TensorFlow/Keras LSTM sequence forecaster.
- [x] Report regression MAE/RMSE and directional accuracy/precision/recall/F1 against a persistence baseline.
- [x] Store immutable model artifacts with checksums and PostgreSQL version metadata; explicit activation.
- [x] Add authenticated inference and model-information endpoints.
- [x] Return direction probability, expected return, forecast price and historical risk estimates with timestamps.
- [x] Rank supported trained assets and report unavailable/stale models explicitly.
- [x] Backtest only held-out observations with a next-bar execution rule, fees and drawdown reporting.
- [x] Add offline tests, including real small RF/XGBoost/LSTM training and artifact round-trip.
- [x] Document training, activation, migration, model storage, limitations and deployment.
- [ ] Pass GitHub Actions and open a feature PR; owner performs merge.

## Scope decisions

One-step forecasts use fully closed candles of one symbol and interval. The three models are versioned as one bundle. Training runs through an operator CLI in a separate process, not an HTTP request. Predictions do not place orders; trading, holdings and exchange credentials remain later phases. Confidence is the classifier's uncalibrated probability, not a promise of accuracy. Validation residuals and recent volatility are estimates, not guarantees.

## Data and verification

Initial training requires sufficient persisted history with continuous candles. Synthetic fixtures verify engineering behavior only; model usefulness must be assessed on real held-out market data. No production performance or profitability claim follows from passing CI.
