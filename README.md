# AI Crypto Trading Platform

Educational AI-based cryptocurrency trading, prediction, portfolio, and automated spot-trading platform based on the project SRS/SDD.

The repository is being delivered feature-by-feature. The current implementation includes the project foundation and the authentication backend. The canonical implementation roadmap is maintained in [`docs/PROJECT_EXECUTION_PLAN.md`](docs/PROJECT_EXECUTION_PLAN.md).

## Current implementation

Available now:

- FastAPI backend with versioned `/api/v1` routes
- React + TypeScript + Vite frontend shell
- PostgreSQL, MongoDB, and Redis foundation
- Docker / Docker Compose development environment
- User registration and email verification flow
- bcrypt password hashing with cost factor 12
- JWT access and refresh tokens
- Refresh-token rotation and logout/revocation
- Protected current-user endpoint
- Failed-login temporary account lockout
- `trader` / `admin` role groundwork
- Optional TOTP two-factor authentication
- GitHub Actions backend/frontend CI

The frontend authentication screens are not implemented yet. For the authentication phase, interact with the backend through Swagger UI, curl, Postman, or another HTTP client.

## Technology stack

| Area | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python 3.12, FastAPI, Pydantic |
| Relational database | PostgreSQL 16 |
| Market/time-series database | MongoDB 7 |
| Cache/transient state | Redis 7 |
| Authentication | bcrypt, JWT, TOTP |
| Containers | Docker, Docker Compose |
| Reverse proxy/frontend container | Nginx |
| Backend testing | Pytest |
| Frontend testing | Vitest, React Testing Library |
| CI | GitHub Actions |

## Prerequisites

### Recommended: Docker setup

Install:

- Git
- Docker Desktop, or Docker Engine with Docker Compose v2

Docker Compose runs PostgreSQL, MongoDB, Redis, the FastAPI backend, and the frontend together.

### Optional: manual development setup

If you want to run the backend/frontend directly on your machine, install:

- Python 3.12+
- Node.js 22+
- npm
- Docker for PostgreSQL/MongoDB/Redis, or install those services separately

## Clone the project

```bash
git clone https://github.com/Zain9192/crypto_trading_platform.git
cd crypto_trading_platform
```

Use `main` for the latest merged/stable work:

```bash
git checkout main
git pull
```

If you are reviewing an open feature branch, explicitly check out that branch instead.

## Environment configuration

Copy the provided environment template:

### macOS / Linux

```bash
cp .env.example .env
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

Before starting the backend, replace the placeholder authentication secrets in `.env`.

### Generate `JWT_SECRET_KEY`

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into:

```env
JWT_SECRET_KEY=<generated-value>
```

### Generate `AUTH_DATA_ENCRYPTION_KEY`

This must be a valid Fernet-compatible key. It is used to encrypt authentication-sensitive data such as stored TOTP secrets.

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Copy the generated value into:

```env
AUTH_DATA_ENCRYPTION_KEY=<generated-value>
```

### Environment variables

The default `.env.example` contains:

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

JWT_SECRET_KEY=replace-with-a-long-random-secret-at-least-32-characters
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_MINUTES=1440
JWT_REFRESH_TOKEN_MINUTES=10080
EMAIL_VERIFICATION_TOKEN_MINUTES=1440
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15

AUTH_DATA_ENCRYPTION_KEY=replace-with-a-valid-fernet-key
TOTP_ISSUER=AI Crypto Trading Platform
```

Important configuration notes:

- Do not commit your real `.env` file.
- Change `POSTGRES_PASSWORD` from the development default when appropriate.
- `JWT_SECRET_KEY` must be at least 32 characters.
- `AUTH_DATA_ENCRYPTION_KEY` must be a valid Fernet-compatible key.
- The provided database hostnames (`postgres`, `mongodb`, `redis`) are Docker Compose service names.
- For a backend running directly on your host machine, use `localhost` for those hosts instead.

## Recommended startup: Docker Compose

After creating `.env` and setting both authentication secrets:

```bash
docker compose up --build
```

To start in the background:

```bash
docker compose up --build -d
```

The services will be available at:

| Service | Address |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger API docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health endpoint | http://localhost:8000/api/v1/health |
| PostgreSQL | localhost:5432 |
| MongoDB | localhost:27017 |
| Redis | localhost:6379 |

Check running containers:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

Backend-only logs:

```bash
docker compose logs -f backend
```

Stop the project:

```bash
docker compose down
```

### Database initialization note

On a fresh PostgreSQL volume, the SQL files in `database/postgres/` are automatically executed in filename order, including the authentication migration.

If you created the PostgreSQL Docker volume before the authentication migration was added, Docker will not automatically rerun initialization scripts. For early development, the simplest reset is:

```bash
docker compose down -v
docker compose up --build
```

`docker compose down -v` deletes local Docker database volumes and therefore removes local development data. Do not use it on data you need to preserve.

## Manual backend development

You can run only the data stores in Docker and run FastAPI directly on your machine.

Start the data services:

```bash
docker compose up -d postgres mongodb redis
```

Create a backend-specific environment file:

### macOS / Linux

```bash
cp .env.example backend/.env
```

### Windows PowerShell

```powershell
Copy-Item .env.example backend/.env
```

In `backend/.env`, change these values:

```env
POSTGRES_HOST=localhost
MONGO_HOST=localhost
REDIS_HOST=localhost
```

Also set valid `JWT_SECRET_KEY` and `AUTH_DATA_ENCRYPTION_KEY` values as described above.

Create and activate a virtual environment:

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

Install dependencies and start FastAPI:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open:

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

The current frontend is still the project shell. Authentication can currently be exercised through the API rather than through frontend forms.

## Interacting with the authentication API

The easiest option is Swagger UI:

```text
http://localhost:8000/docs
```

You can also use curl or Postman.

### 1. Register a user

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "demo_user",
    "email": "demo@example.com",
    "password": "StrongPass123!"
  }'
```

Username rules:

- 3 to 50 characters
- letters, numbers, `_`, `.`, and `-` are allowed

Password rules currently enforced by the API:

- minimum 8 characters
- maximum 128 characters
- maximum 72 UTF-8 bytes because bcrypt is used

In `development` and `test` environments, the registration response includes a temporary `verification_token` so the verification flow can be tested before the email-notification feature is implemented. Production responses do not expose this raw token.

### 2. Verify the email

Copy the `verification_token` returned during development registration:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/verify-email" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "PASTE_VERIFICATION_TOKEN_HERE"
  }'
```

A user must verify their email before normal login succeeds.

### 3. Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "StrongPass123!"
  }'
```

The response contains:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

By default:

- access token lifetime: 24 hours
- refresh token lifetime: 7 days

### 4. Call a protected endpoint

Use the access token:

```bash
curl "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

In Swagger UI, click **Authorize** and provide your bearer token, then protected endpoints can be tested directly from the browser.

### 5. Refresh a session

```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "YOUR_REFRESH_TOKEN"
  }'
```

Refresh tokens are rotated. Use the new refresh token returned by the refresh response for the next refresh operation.

### 6. Configure TOTP two-factor authentication

First create a TOTP setup using an authenticated request:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/2fa/setup" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

The response contains a TOTP `secret` and `otpauth_uri`. Add it to a compatible authenticator application.

Enable 2FA using a current six-digit code:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/2fa/enable" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "123456"
  }'
```

Once enabled, include `totp_code` when logging in:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "StrongPass123!",
    "totp_code": "123456"
  }'
```

Disable 2FA using the user's password and a current TOTP code:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/2fa/disable" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "password": "StrongPass123!",
    "code": "123456"
  }'
```

### 7. Logout

Logout revokes the supplied refresh token:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/logout" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "YOUR_REFRESH_TOKEN"
  }'
```

An already-issued access token is stateless and remains valid until its configured expiration time. The revoked refresh token cannot be used to obtain a new token pair.

## Authentication endpoints

| Method | Endpoint | Authentication required | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | No | Create a trader account |
| POST | `/api/v1/auth/verify-email` | No | Verify a registration token |
| POST | `/api/v1/auth/login` | No | Authenticate and obtain tokens |
| POST | `/api/v1/auth/refresh` | No | Rotate refresh token and obtain a new token pair |
| POST | `/api/v1/auth/logout` | No | Revoke a refresh token |
| GET | `/api/v1/auth/me` | Bearer access token | Read the current user |
| POST | `/api/v1/auth/2fa/setup` | Bearer access token | Generate TOTP setup data |
| POST | `/api/v1/auth/2fa/enable` | Bearer access token | Enable TOTP after code verification |
| POST | `/api/v1/auth/2fa/disable` | Bearer access token | Disable TOTP after password/code verification |

## Login protection

The current authentication implementation includes failed-login protection. The default values are:

```env
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15
```

After the configured number of failed attempts, login is temporarily locked for the configured duration.

## Running tests

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm test
npm run build
```

GitHub Actions runs backend tests, frontend tests, and the frontend build for feature branches and pull requests.

## Useful development commands

Rebuild containers after dependency or Dockerfile changes:

```bash
docker compose up --build
```

Restart only the backend:

```bash
docker compose restart backend
```

Open a PostgreSQL shell:

```bash
docker compose exec postgres psql -U crypto_user -d crypto_trading
```

Open a Redis CLI:

```bash
docker compose exec redis redis-cli
```

Open a Mongo shell:

```bash
docker compose exec mongodb mongosh crypto_market
```

## Security notes

- Never commit `.env`, passwords, JWT secrets, encryption keys, exchange credentials, or real API tokens.
- Development defaults are not production credentials.
- Use independently generated production secrets.
- Use HTTPS/TLS in deployed environments.
- Do not use real exchange funds during normal development or automated testing.
- Authentication and exchange secrets must never be printed to application logs.

## Project workflow

Work is delivered one feature at a time:

1. Start from the latest merged `main`.
2. Create `feature/<feature-name>`.
3. Implement only the planned feature scope.
4. Add/update tests.
5. Push the feature branch.
6. Wait for GitHub Actions.
7. Fix every failing check on the same feature branch.
8. Open a PR into `main` after the feature is review-ready.
9. The project owner performs the merge.
10. Start the next feature from the newly updated `main`.

See [`docs/PROJECT_EXECUTION_PLAN.md`](docs/PROJECT_EXECUTION_PLAN.md) for the fixed project sequence, architecture decisions, and scope controls.

## Planned sequence

1. Foundation — complete
2. Authentication — implemented in the authentication feature
3. Market data
4. AI/ML prediction
5. Portfolio and risk
6. Exchange integration
7. Automated trading engine
8. Alerts, notifications, and reports
9. Admin
10. QA/security hardening
11. Deployment/operations
