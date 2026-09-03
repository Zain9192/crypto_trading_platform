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
