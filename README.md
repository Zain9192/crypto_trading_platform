# AI Crypto Trading Platform

Educational AI-based cryptocurrency trading, prediction, portfolio, and automated spot-trading platform based on the project SRS/SDD.

The repository is delivered feature-by-feature. The canonical implementation roadmap lives in [`docs/PROJECT_EXECUTION_PLAN.md`](docs/PROJECT_EXECUTION_PLAN.md).

## Current implementation

Available now:

- FastAPI backend with versioned `/api/v1` routes
- React + TypeScript + Vite frontend
- PostgreSQL, MongoDB, and Redis foundation
- Docker / Docker Compose local environment
- User registration, email verification, JWT access/refresh tokens, logout/revocation, failed-login lockout, roles, and optional TOTP 2FA
- Top-50 cryptocurrency market feed using CoinGecko public market data
- Historical OHLCV candles using Binance public market endpoints
- Supported chart intervals: `1h`, `4h`, `1d`, `1w`, `1M`
- MongoDB OHLCV persistence
- Redis market and OHLCV cache
- Live market WebSocket feed with a default 30-second refresh cadence
- Candlestick chart using TradingView Lightweight Charts
- SMA, EMA, RSI, MACD, Bollinger Bands, and volume indicators
- GitHub Actions backend/frontend CI

The market dashboard is available in the frontend. Authentication is currently exercised through Swagger UI, curl, Postman, or another HTTP client because dedicated frontend auth screens are not implemented yet.

## Technology stack

| Area | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite, TanStack Query |
| Charts | TradingView Lightweight Charts |
| Backend | Python 3.12, FastAPI, Pydantic |
| Relational database | PostgreSQL 16 |
| Market/time-series database | MongoDB 7 |
| Cache/transient state | Redis 7 |
| Public market providers | CoinGecko, Binance public market API |
| Authentication | bcrypt, JWT, TOTP |
| Containers | Docker, Docker Compose |
| Reverse proxy | Nginx |
| Backend testing | Pytest |
| Frontend testing | Vitest, React Testing Library |
| CI | GitHub Actions |

## Prerequisites

### Recommended Docker setup

Install:

- Git
- Docker Desktop, or Docker Engine with Docker Compose v2

Docker Compose runs PostgreSQL, MongoDB, Redis, the FastAPI backend, and the frontend together.

### Optional manual development setup

Install:

- Python 3.12+
- Node.js 22+
- npm
- Docker for PostgreSQL/MongoDB/Redis, or install those services separately

## Clone the project

```bash
git clone https://github.com/Zain9192/crypto_trading_platform.git
cd crypto_trading_platform
git checkout main
git pull
```

To review a feature before it is merged, explicitly check out that feature branch.

## Environment configuration

Create the local environment file.

macOS / Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### Generate `JWT_SECRET_KEY`

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the result in `.env`:

```env
JWT_SECRET_KEY=<generated-value>
```

### Generate `AUTH_DATA_ENCRYPTION_KEY`

This must be a valid Fernet-compatible key and is used to encrypt authentication-sensitive values such as TOTP secrets.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the result in `.env`:

```env
AUTH_DATA_ENCRYPTION_KEY=<generated-value>
```

### Important environment variables

```env
APP_NAME=AI Crypto Trading Platform
APP_ENV=development
API_V1_PREFIX=/api/v1
BACKEND_PORT=8000
FRONTEND_PORT=5173

POSTGRES_DB=crypto_trading
POSTGRES_USER=crypto_user
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

MONGO_DB=crypto_market
MONGO_HOST=mongodb
MONGO_PORT=27017

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

JWT_SECRET_KEY=replace-with-a-long-random-secret-at-least-32-characters
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_MINUTES=1440
JWT_REFRESH_TOKEN_MINUTES=10080
EMAIL_VERIFICATION_TOKEN_MINUTES=1440
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15

AUTH_DATA_ENCRYPTION_KEY=replace-with-a-valid-fernet-key
TOTP_ISSUER=AI Crypto Trading Platform

COINGECKO_BASE_URL=https://api.coingecko.com/api/v3
BINANCE_MARKET_BASE_URL=https://api.binance.com
MARKET_DEFAULT_QUOTE_ASSET=USDT
MARKET_REFRESH_SECONDS=30
MARKET_CACHE_TTL_SECONDS=25
OHLCV_CACHE_TTL_SECONDS=60
MARKET_HTTP_TIMEOUT_SECONDS=10
```

Notes:

- Never commit your real `.env` file.
- Change the default PostgreSQL password when appropriate.
- `JWT_SECRET_KEY` must be at least 32 characters.
- `AUTH_DATA_ENCRYPTION_KEY` must be a valid Fernet key.
- The provider URLs above use public endpoints and currently require no exchange credentials.
- Docker uses service hostnames such as `postgres`, `mongodb`, and `redis`.
- When running the backend directly on your machine, use `localhost` for the database/cache hosts.

## Start the full project with Docker Compose

```bash
docker compose up --build
```

Background mode:

```bash
docker compose up --build -d
```

Services:

| Service | Address |
| --- | --- |
| Frontend market dashboard | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger API docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health endpoint | http://localhost:8000/api/v1/health |
| PostgreSQL | localhost:5432 |
| MongoDB | localhost:27017 |
| Redis | localhost:6379 |

Useful Docker commands:

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose down
```

## Database initialization

On a fresh PostgreSQL volume, SQL files in `database/postgres/` are executed in filename order.

MongoDB initialization creates the `market_data` collection and its unique `symbol + interval + timestamp` index.

If an early local Docker volume was created before a database initialization change and you do not need to preserve local data, reset it with:

```bash
docker compose down -v
docker compose up --build
```

`docker compose down -v` deletes local Docker database volumes. Do not run it against data you need to keep.

## Manual backend development

Start the data stores:

```bash
docker compose up -d postgres mongodb redis
```

Create `backend/.env` from the root template and change the service hosts:

```env
POSTGRES_HOST=localhost
MONGO_HOST=localhost
REDIS_HOST=localhost
```

Then:

```bash
cd backend
python -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and run:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open Swagger:

```text
http://localhost:8000/docs
```

## Manual frontend development

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Vite proxies `/api` and WebSocket traffic to the backend on `localhost:8000` during local development. The production frontend Nginx container proxies the same `/api` path to the backend container.

## Market data interaction

The market endpoints are public read-only research endpoints.

### Top 50 assets

```bash
curl "http://localhost:8000/api/v1/market/assets?limit=50"
```

The response includes current USD price, market cap/rank, 24-hour change, high/low, volume, supply, and provider update time where available. Redis caches this feed and individual latest asset snapshots.

### One asset from the top-50 set

```bash
curl "http://localhost:8000/api/v1/market/assets/BTC"
```

### Historical OHLCV

```bash
curl "http://localhost:8000/api/v1/market/ohlcv/BTC?interval=1d&limit=200"
```

Supported intervals:

- `1h`
- `4h`
- `1d`
- `1w`
- `1M`

Historical candles are fetched from Binance public market data, normalized by the backend, cached in Redis, and persisted to MongoDB.

A top-50 asset may not have a matching `SYMBOL/USDT` market on Binance. In that case, the OHLCV endpoint returns a provider error instead of fabricating data.

### Technical indicators

```bash
curl "http://localhost:8000/api/v1/market/indicators/BTC?interval=1d&limit=200"
```

The response contains calculated:

- SMA 20
- EMA 20
- RSI 14
- MACD
- MACD signal
- MACD histogram
- Bollinger middle/upper/lower bands
- volume

### Live price WebSocket

Connect to:

```text
ws://localhost:8000/api/v1/market/ws/prices?limit=50
```

The server sends `market_snapshot` frames on the configured `MARKET_REFRESH_SECONDS` cadence. The frontend connects through the same `/api` proxy path automatically.

### Market endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/market/assets` | Top market-cap assets, maximum 50 |
| GET | `/api/v1/market/assets/{symbol}` | One asset from the top-50 set |
| GET | `/api/v1/market/ohlcv/{symbol}` | Historical normalized OHLCV |
| GET | `/api/v1/market/indicators/{symbol}` | Technical indicators derived from OHLCV |
| WS | `/api/v1/market/ws/prices` | Live market snapshot stream |

Automated tests mock external market-provider calls. CI does not depend on live CoinGecko or Binance responses.

## Authentication interaction

Swagger UI is the easiest way to exercise authentication:

```text
http://localhost:8000/docs
```

### Register

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_user","email":"demo@example.com","password":"StrongPass123!"}'
```

In `development` and `test`, the response exposes the raw verification token so email verification can be tested before the notification phase. Production responses do not expose it.

### Verify email

```bash
curl -X POST "http://localhost:8000/api/v1/auth/verify-email" \
  -H "Content-Type: application/json" \
  -d '{"token":"PASTE_VERIFICATION_TOKEN_HERE"}'
```

### Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"StrongPass123!"}'
```

### Protected current user

```bash
curl "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Refresh

```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
```

Refresh tokens rotate. Use the newly returned refresh token on the next refresh.

### TOTP 2FA

Setup:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/2fa/setup" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Enable:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/2fa/enable" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}'
```

Once enabled, supply `totp_code` during login.

### Logout

```bash
curl -X POST "http://localhost:8000/api/v1/auth/logout" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
```

Logout revokes the refresh token. Already-issued access tokens remain valid until their configured expiry.

## Running tests

Backend:

```bash
cd backend
python -m pip install -r requirements.txt
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm install
npm test
npm run build
```

GitHub Actions runs backend tests, frontend tests, and the frontend production build for feature branches and pull requests.

## Useful development commands

```bash
docker compose restart backend
docker compose exec postgres psql -U crypto_user -d crypto_trading
docker compose exec redis redis-cli
docker compose exec mongodb mongosh crypto_market
```

## Security and usage notes

- This is an educational platform and not financial advice.
- Never commit `.env`, passwords, JWT secrets, encryption keys, exchange credentials, or real API tokens.
- Use independently generated production secrets.
- Use HTTPS/TLS in deployed environments.
- Do not use real exchange funds during normal development or automated testing.
- Authentication and future exchange secrets must never be printed to logs.
- Market provider errors must be surfaced rather than replaced with fabricated values.

## Project workflow

1. Start from the latest merged `main`.
2. Create `feature/<feature-name>`.
3. Implement only the planned feature scope.
4. Add/update tests.
5. Push the feature branch.
6. Wait for GitHub Actions.
7. Fix every failing check on the same feature branch.
8. Open a PR into `main` only when the feature is review-ready and CI is green.
9. The project owner performs the merge.
10. Start the next feature from the newly updated `main`.

## Planned sequence

1. Foundation — complete
2. Authentication — complete
3. Market data — current
4. AI/ML prediction
5. Portfolio and risk
6. Exchange integration
7. Automated trading engine
8. Alerts, notifications, and reports
9. Admin
10. QA/security hardening
11. Deployment/operations

See [`docs/PROJECT_EXECUTION_PLAN.md`](docs/PROJECT_EXECUTION_PLAN.md) for the fixed scope and architecture rules.


## Phase 3 background ingestion and stored history

`docker compose up --build` also starts the `market-ingestion` worker. For a local Python setup with MongoDB and Redis available, run this from `backend`:

```bash
python -m app.market.workers.ingestion
```

The worker refreshes the top-50 price cache separately from historical ingestion. It fetches a bounded window for each supported Binance pair and all five chart intervals, and upserts by symbol/interval/timestamp. Existing candles update without duplicate records. Unsupported pairs and temporary failures are logged and retried next cycle.

| Setting | Default | Behavior |
| --- | --- | --- |
| `MARKET_REFRESH_SECONDS` | 30 | Price refresh and frontend polling cadence in seconds |
| `MARKET_HISTORY_REFRESH_SECONDS` | 900 | Delay between completed history cycles |
| `MARKET_HISTORY_CANDLE_LIMIT` | 500 | Candles per asset/interval, from 20 to 1000 |
| `MARKET_INGESTION_REQUEST_SPACING_SECONDS` | 0.25 | Pause between history requests |

A full history cycle can take several minutes and does not block the price loop. Adjust cadence and pacing for the provider's quota. Candle responses may remain cached for `OHLCV_CACHE_TTL_SECONDS` even when the frontend polls more frequently.

Read the saved history with:

```bash
curl "http://localhost:8000/api/v1/market/history/BTC?interval=1d&limit=200"
```

This endpoint returns `source: mongodb`, an empty list if no history has been stored, and HTTP 503 when storage is unavailable. It does not silently substitute old history into the live OHLCV endpoint. Stored history may be older than the current market.

Indicators use TA-Lib, as specified in the plan. Warm-up values are null until enough candles exist. The candlestick chart includes volume bars and preserves zoom/pan during automatic refresh.

SonarQube is deferred at the owner's request; its workflow and project configuration have been removed. Backend tests, frontend tests/build, and the existing Checkstyle job remain in CI.


## Phase 4 — AI/ML prediction

The step-by-step implementation checklist is in [docs/PHASE_4_CHECKLIST.md](docs/PHASE_4_CHECKLIST.md). Training is an offline operator task; authenticated API calls only perform inference and record forecasts.

### 1. Prepare the database and history

For an existing PostgreSQL volume, apply the additive migration (fresh Compose volumes run it automatically):

```bash
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/postgres/003_prediction.sql
```

Fresh setups default to `MARKET_HISTORY_CANDLE_LIMIT=500` (up to 1000), sufficient for the default training lookback once ingestion completes. Existing installations with `MARKET_HISTORY_CANDLE_LIMIT=200` in `.env` must update it to 500 and restart ingestion; an explicit environment setting overrides the new default. The worker needs at least 200 supervised samples after indicator warm-up and sequence construction; 300 or more stored continuous candles are required in practice. Unsupported pairs, zero-volume windows, missing/duplicate candles and unclosed candles are not silently fabricated or filled.

```bash
docker compose up -d --build backend market-ingestion
```

### 2. Train a candidate version

```bash
docker compose --profile training run --rm prediction-trainer --symbol BTC --interval 1d --limit 1000 --lookback 20 --epochs 10 --trees 100
```

For a local Python setup, install `backend/requirements.txt`, set `PREDICTION_ARTIFACT_DIR` to a trusted directory shared by the training process and API, then run from `backend`:

```bash
python -m app.prediction.train --symbol BTC --interval 1d --limit 1000
```

Training outputs a version identifier, validation/test metrics and held-out backtest results. It creates an inactive candidate by default. Review the metrics against the included no-change price baseline before activation. RF confidence is uncalibrated; passing training or CI does not establish market performance. Only closed candles are used; the forecast horizon is one candle of the selected interval.

### 3. Activate or roll back a version explicitly

```bash
docker compose --profile training run --rm prediction-trainer --activate-version YOUR_VERSION_UUID
```

The command verifies the bundle before atomically changing the active version for that symbol/interval. The same command can select an older retained version to roll back. `--activate` on a training command is an explicit alternative that activates the newly evaluated bundle immediately. Models are operator-created; never replace artifact files with untrusted serialized models. Back up the PostgreSQL registry and artifact volume together. Runtime package versions must match the stored manifest; use a matching image or retrain after upgrades.

### 4. Query predictions and opportunities

Use an access token from the existing authentication flow:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" "http://localhost:8000/api/v1/predictions/BTC?interval=1d"
curl -H "Authorization: Bearer $ACCESS_TOKEN" "http://localhost:8000/api/v1/predictions/models/BTC?interval=1d"
curl -X POST -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json"   -d '{"symbols":["BTC","ETH"],"interval":"1d"}' "http://localhost:8000/api/v1/predictions/opportunities"
```

Forecasts include model version, data close time (`as_of`), forecast target close time, current/predicted price, RF direction/up probability, confidence, expected return, recent candle volatility, and validation absolute-error percentile. Expected returns and risk values are fractions (`0.01` means 1%). The classifier's direction and the regressors' forecast may disagree; they are separate estimates. Inactive/missing models or stale history return HTTP 503; invalid history returns HTTP 422. Ranking reports unavailable assets explicitly, compares one interval at a time, and places no orders.

### 5. Evaluate and verify

Evaluation uses ordered 70%/15%/15% partitions with one purged label sample at each boundary. Scaling and all model fitting use only train data. Validation residuals supply the error estimate, while regression MAE/RMSE, directional accuracy/precision/recall/F1, the persistence baseline and delayed long/cash backtest are reported separately on held-out test data. Fees default to 10 basis points per transition; the backtest is a simplified educational simulator without spread, liquidity, slippage or an exchange order book.

Run tests from `backend` with `python -m pytest -q`. The model test trains all three algorithms on synthetic candles and verifies save/load and inference. PostgreSQL tests use only `PREDICTION_TEST_DSN` when supplied; CI provisions a disposable database. Local runs without that service explicitly skip the registry integration test. No trained production model, real-data performance result or live trading capability is shipped in this phase.

## Phase 5 — Portfolio and risk

The **Portfolio & risk** tab now provides sign-in/registration/verification, a virtual USD portfolio, holdings and allocation, cash reservations, average-cost P&L, risk settings, and paginated paper-trade history. Sessions stay in memory and refresh automatically; reloading the page requires signing in again.

For existing PostgreSQL volumes, apply the additive migration before starting the updated backend (fresh Compose volumes apply SQL files automatically):

```bash
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/postgres/004_portfolio.sql
docker compose up -d --build
```

Keep existing volumes; do not use `down -v` to upgrade. If upgrading from before Phase 2, apply `002_auth.sql` and `003_prediction.sql` first. The Phase 5 migration is rerunnable and leaves foundation portfolio records in `legacy` mode.

### Frontend walkthrough

1. Open the frontend at `http://localhost:5173` for Vite development, or `http://localhost:5173` for Compose (or your configured `FRONTEND_PORT`). Choose **Portfolio & risk**.
2. Sign in with a verified account (enter a 2FA code if enabled). For a new development account, choose **Create account**, register, confirm the supplied development verification token, then sign in. Production email delivery remains a later phase; the backend does not return development tokens in production.
3. Create a paper portfolio with **1,000 virtual USD**. Creation is idempotent: a repeat returns your existing portfolio and never adds more cash.
4. Reserve a **BTC buy**, quantity **2**, simulation price **100 USD**, fee **2 USD**. Available cash becomes **798**, reserved cash **202**. The default recorded stop/target are **95 / 110 USD**.
5. Choose **Fill paper trade**. Cash becomes **798**, holding quantity **2**, cost basis **202**, average cost **101**. Market valuation uses the current public price, so it will not equal the simulation price.
6. Reserve and fill a **BTC sell**, quantity **1**, simulation price **120 USD**, fee **1 USD**. Cash becomes **917**, remaining basis **101**, and realized P&L **18 USD**. Check the fill in **Trade history**.
7. Set **Maximum open positions** to **1**, then attempt an ETH buy while holding BTC: the server rejects it. Reserve a BTC sell and cancel it to see available quantity restored.

All prices entered in the trade form are **simulation inputs**, not live execution quotes. There are no real deposits, exchange calls, or automatic orders. Stop-loss/take-profit settings are recorded on new buys; monitoring and automatic execution belong to Phase 7. Changing settings does not retroactively change accepted reservations.

### Accounting and valuation

- PostgreSQL is authoritative. Every state change locks the owned portfolio row and commits holdings, cash, order status and fill history together. Concurrent reservations cannot reuse cash or sell the same units.
- Buy fees increase cost basis; sell fees reduce realized proceeds. Partial sales remove proportional average cost, and the final sale removes all remaining basis. Monetary storage and API strings use eight decimal places, with half-even rounding.
- Available cash is cash minus pending buy notional and fees. Available holding quantity excludes pending sells. Pending buys reserve position slots. Maximum open trades counts all pending reservations; completed fills do not count.
- Buy investment bounds include fees; sell exits bypass investment bounds but still require available units and an open-trade slot. Changing position/trade limits below existing usage is rejected.
- Holdings use CoinGecko's top-50 USD prices only when timestamped within five minutes (up to 30 seconds clock skew). Missing, stale, or unsupported prices produce `null` total valuation/P&L/allocation and an explicit list of unpriced symbols; cash and realized P&L remain valid. Public reference valuation is distinct from simulated fill prices.
- One paper portfolio per user. IDs are ownership-checked on every endpoint; another user's portfolio/order returns 404. Client order UUIDs provide retry idempotency; reusing one with different details returns 409. Fill/cancel retries are idempotent, conflicting terminal actions return 409.

### Portfolio API

All routes require the existing bearer authentication under `/api/v1`.

| Method | Route | Purpose |
| --- | --- | --- |
| GET / POST | `/portfolios` | List owned portfolios / create once with `initial_cash` |
| GET | `/portfolios/{id}` | Balances, P&L, allocation, holdings, pending trades, risk settings |
| PUT | `/portfolios/{id}/risk` | Replace investment limits, max positions/trades, optional stop/target percentages |
| POST | `/portfolios/{id}/orders/preview` | Check current risk and balances without reserving |
| POST | `/portfolios/{id}/orders` | Reserve a paper order; checks risk again atomically |
| POST | `/portfolios/{id}/orders/{order_id}/fill` | Record a simulated fill at its saved price/fee |
| POST | `/portfolios/{id}/orders/{order_id}/cancel` | Release a pending reservation |
| GET | `/portfolios/{id}/trades?limit=25&before=123` | Newest-first fills; follow `next_cursor` as `before` |

Paper order bodies contain `client_order_id` (UUID), `symbol`, `side` (`buy`/`sell`), `quantity`, `simulation_price`, and `fee`. Use decimal strings. Risk fields are `min_investment`, `max_investment`, `max_open_positions`, `max_open_trades`, `stop_loss_pct`, and `take_profit_pct`; `null` disables a percentage threshold. Validation failures return 422, conflicts 409, and storage outages 503.

Automated tests use synthetic prices. PostgreSQL accounting, ownership, cursor pagination, repeated fills and concurrent reservations run on CI's disposable `PREDICTION_TEST_DSN` service (also reused by the model registry tests). No live exchange funds or production database are used.
