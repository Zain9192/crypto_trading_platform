# AI Crypto Trading Platform — Execution Plan

This document is the canonical implementation plan for the repository. All future feature work should follow this plan unless the project owner explicitly approves a change.

## 1. Project scope

Build an educational full-stack AI cryptocurrency trading platform with:

- User registration, verification, login, JWT sessions, optional 2FA, and roles.
- Real-time cryptocurrency market data and OHLCV history.
- Candlestick charts and technical indicators.
- AI/ML price and direction predictions with confidence, expected return, and risk.
- Opportunity ranking across supported assets.
- Exchange connectivity for Binance, Coinbase, and Kraken.
- Automated spot trading only for V1.
- Portfolio, holdings, realized/unrealized P&L, and risk controls.
- Trade history, alerts, notifications, CSV/PDF reporting, and admin monitoring.

V1 does not include margin or futures trading.

## 2. Fixed technology choices

### Frontend
- React
- TypeScript
- Vite
- Tailwind CSS
- TanStack Query when API state management is needed
- TradingView Lightweight Charts for market charts

### Backend
- Python 3.12
- FastAPI
- Pydantic / pydantic-settings
- REST APIs under `/api/v1`
- WebSockets for live data/notifications where appropriate

### Data
- PostgreSQL: users, auth, roles, portfolios, holdings, orders, bots, alerts, prediction/model metadata
- MongoDB: historical OHLCV and market/time-series documents
- Redis: live price cache, short-lived state, rate limits, temporary tokens/cache

### AI/ML
- pandas
- NumPy
- scikit-learn
- XGBoost
- TensorFlow/Keras for LSTM
- pandas-ta or TA-Lib for indicators

### Exchange and market integration
- CCXT for common exchange operations
- Binance, Coinbase, Kraken adapters
- CoinGecko/CryptoCompare may be used for public market/reference data where appropriate

### DevOps and quality
- Docker
- Docker Compose for local development
- Nginx
- GitHub Actions
- Pytest
- Vitest/React Testing Library
- Playwright later for end-to-end testing
- Locust or k6 later for load testing

## 3. Architecture rule

Start as a modular FastAPI application with strong module boundaries. Do not create unnecessary distributed microservices early. Split heavy/background concerns into separate workers/containers when needed, especially:

- Market ingestion worker
- Prediction/training worker
- Trading execution worker

PostgreSQL remains the source of truth for users, money-related state, and orders.

## 4. Delivery and Git workflow

Every feature must follow this process:

1. Confirm `main` contains the latest approved work.
2. Create one dedicated branch: `feature/<feature-name>`.
3. Implement only the planned feature scope plus necessary tests/configuration.
4. Run relevant backend/frontend/unit/integration tests.
5. Push the feature branch.
6. Wait for GitHub Actions CI to finish.
7. Fix all failing checks on the same feature branch before review.
8. Open a PR into `main` only after the feature is complete enough for review.
9. Do not merge the PR automatically. The project owner performs the merge.
10. Start the next feature from the newly updated `main` after the previous PR is merged.

No feature should be considered complete while CI is red.

## 5. Implementation phases

### Phase 1 — Foundation — COMPLETE

Branch: `feature/foundation`

Delivered:
- Repository structure
- FastAPI application shell
- React + TypeScript frontend shell
- PostgreSQL, MongoDB, Redis foundation
- Docker/Docker Compose
- Nginx
- Environment template
- Initial SQL/data-store setup
- Health endpoint
- GitHub Actions CI
- Basic backend/frontend tests

### Phase 2 — Authentication — COMPLETE

Branch: `feature/authentication`

Implement:
- User registration
- Unique email validation
- Password hashing using bcrypt with cost factor >= 12
- Login
- JWT access tokens
- Refresh tokens
- Logout/revocation strategy
- Email verification token flow
- User roles (`trader`, `admin`)
- Current-user endpoint
- Login-attempt protection/lockout groundwork
- Optional TOTP/2FA structure if practical within the SRS scope
- Database changes required for auth
- API validation/error responses
- Unit/integration tests for all auth flows

Security rules:
- Never store plaintext passwords.
- Never log passwords, tokens, secrets, or exchange credentials.
- Keep secret keys in environment variables; do not hardcode production secrets.
- Validate all inputs server-side.

Definition of done:
- Registration, login, refresh, protected-user lookup, verification flow, and negative cases are tested.
- Existing health tests remain green.
- Frontend build/tests remain green.
- GitHub Actions push and PR checks pass.

### Phase 3 — Market Data — CURRENT

Branch: `feature/market-data`

Implement:
- Public market provider/exchange integration
- Top-50 asset list
- Normalized OHLCV model
- Historical OHLCV ingestion
- MongoDB persistence
- Redis latest-price cache
- Market REST endpoints
- Live-price WebSocket channel
- Candlestick chart integration
- RSI, MACD, EMA, MA, Bollinger Bands, volume indicators
- Tests with provider calls mocked

### Phase 4 — AI/ML Prediction

Implement:
- Training dataset pipeline
- Chronological train/validation/test splitting; never random-split time series
- Feature engineering from OHLCV and indicators
- Random Forest directional model
- XGBoost price/regression model
- LSTM forecasting model
- MAE/RMSE evaluation for regression
- Accuracy/precision/recall/F1 for classification
- Model version metadata/registry
- Prediction service/API
- Confidence, expected-return, and estimated-risk output
- Opportunity ranking engine
- Backtesting/evaluation utilities

### Phase 5 — Portfolio and Risk

Implement:
- Portfolio model/service
- Holdings
- Asset allocation
- Realized P&L
- Unrealized P&L
- Available-balance calculations
- Investment amount limits
- Stop-loss/take-profit settings
- Maximum open positions/trades
- Risk validation service
- Portfolio/trade-history APIs and UI

### Phase 6 — Exchange Integration

Implement an exchange abstraction with operations similar to:

- `connect`
- `get_balance`
- `get_price`
- `place_order`
- `cancel_order`
- `get_order`
- `get_trades`

Adapters:
- Binance
- Coinbase
- Kraken

Requirements:
- Prefer CCXT when behavior is reliable and consistent.
- Allow native exchange logic where necessary.
- Encrypt stored exchange API credentials.
- Use sandbox/testnet integrations before any live-money testing.

### Phase 7 — Automated Trading Engine

Implement:
- Bot configuration
- Start/stop bot
- Prediction-confidence threshold
- Risk checks before every order
- Balance checks
- Maximum-open-trade checks
- Buy/sell signal handling
- Spot order execution
- Stop-loss/take-profit monitoring
- Order lifecycle/status handling
- Idempotency protections
- Failure/retry handling
- Trade persistence
- Portfolio update after fills
- Execution tests using mocks/sandbox only

Critical rule: do not enable unrestricted live-money execution during normal development or automated tests.

### Phase 8 — Alerts, Notifications, and Reports

Implement:
- Price alerts
- Trade-executed notifications
- Stop-loss/take-profit notifications
- Bot/exchange failure notifications
- In-app/WebSocket notifications
- Email notifications using SendGrid/SMTP-compatible abstraction
- CSV export
- PDF report generation

### Phase 9 — Admin

Implement:
- User administration
- Role-aware admin access
- System health view
- Exchange-provider health
- Model versions and metrics
- Prediction/model health
- Operational logs/status summaries

### Phase 10 — QA and Security Hardening

Implement/validate:
- Functional tests
- API integration tests
- Frontend tests
- End-to-end tests
- Exchange failure/timeout tests
- Rate limiting
- Login attempt limits
- JWT expiration/refresh behavior
- SQL injection protections
- XSS/input validation protections
- Secret handling
- Concurrency tests
- Load tests against stated SRS targets
- ML leakage/drift/backtesting checks

Performance targets to validate later:
- Dashboard under ~2 seconds where feasible
- Prediction under ~5 seconds
- Trade submission path under ~1 second excluding third-party exchange latency where applicable
- Internal API target around 300 ms for standard operations
- 500+ concurrent-user target through load testing

### Phase 11 — Deployment and Operations

Implement:
- Production Docker images
- Production environment configuration
- TLS/HTTPS
- Nginx/reverse proxy
- CI/CD deployment workflow
- Cloud deployment
- Monitoring and error tracking
- Database backups
- Kubernetes only when deployment/scaling requirements justify it

## 6. Database responsibility rules

### PostgreSQL
Use for transactional and relational data including:
- Users
- Roles/auth state
- Exchange connections
- Portfolios/holdings
- Trading bots
- Trade orders/executions
- Alerts
- Prediction metadata
- ML model metadata

### MongoDB
Use for:
- Historical OHLCV
- Time-series market documents
- Indicator-enriched market records where appropriate

### Redis
Use for:
- Latest prices
- Short-lived caches
- Rate-limit counters
- Temporary verification/auth state where appropriate
- Live/prediction cache

## 7. Security baseline

The implementation must preserve these requirements throughout all phases:

- HTTPS/TLS 1.2+ in deployed environments
- bcrypt password hashing with cost factor >= 12
- AES-256-equivalent protection for persisted exchange secrets, with the master key outside source code
- JWT expiration and refresh-token controls
- Rate limiting
- Maximum failed-login protection
- Server-side validation
- SQL injection protections
- XSS-safe frontend patterns
- No plaintext credentials or sensitive tokens in source, logs, commits, or test fixtures

## 8. Testing rule for external systems

Automated tests must not depend on real exchange funds or unstable third-party APIs. Provider/exchange calls should be mocked for unit/integration CI tests. Sandbox/testnet checks may be separate controlled tests.

## 9. Feature sequence — do not reorder without approval

1. Foundation — complete
2. Authentication — complete
3. Market data — current
4. AI/ML prediction
5. Portfolio and risk
6. Exchange integration
7. Automated trading engine
8. Alerts, notifications, reports
9. Admin
10. QA/security hardening
11. Deployment/operations

The dependency chain is intentionally: foundation -> auth/market data -> prediction -> portfolio/risk -> exchange integration -> automated trading -> hardening/deployment.

## 10. Change-control rule

If a future implementation decision conflicts with this document or the SRS/SDD, stop and resolve the conflict before coding. Do not silently change architecture, scope, supported exchanges, trading mode, database responsibility, security requirements, or feature order.

When a plan change is approved, update this file in the same PR that introduces the change so the repository remains the single source of truth.
