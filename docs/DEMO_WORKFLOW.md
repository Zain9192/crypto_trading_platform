# Demo & End-to-End Test Workflow

A step-by-step guide to start the platform, verify every module automatically, and present each module live in the browser.

Verified on 2026-11-14 (Windows 11, Docker Desktop, Compose v5): **57/57 end-to-end checks, 165 backend tests, 16 frontend tests passing.**

| Part | What it covers | Time |
| --- | --- | --- |
| [A. Start the stack](#a-start-the-stack) | Docker services, migrations, market history | 5–15 min (first time) |
| [B. Train AI models](#b-train-the-ai-models) | BTC and ETH forecasts for `1h`, `4h`, `1d`, `1w` | 1–3 min per model (~15–20 min all) |
| [C. Automated end-to-end test](#c-automated-end-to-end-test) | All 11 modules through the API | ~2 min |
| [D. Unit test suites](#d-unit-test-suites) | Backend pytest, frontend Vitest | ~1 min |
| [E. Live browser demo](#e-live-browser-demo-script) | Presenter script, module by module | 15–20 min |
| [F. Troubleshooting](#f-troubleshooting) | Known messages and fixes | — |

---

## A. Start the stack

**Prerequisites:** Docker Desktop running ("Engine running"), and a filled-in `.env` (copy `.env.example`; see the README for generating `JWT_SECRET_KEY`, `AUTH_DATA_ENCRYPTION_KEY` and `EXCHANGE_ENCRYPTION_KEY`). For the exchange/testnet demo, also set `BINANCE_API_KEY`, `BINANCE_SECRET_KEY` from <https://testnet.binance.vision>.

```powershell
cd crypto_trading_platform
docker compose up --build -d
docker compose ps
```

Expected — 8 services `Up`, postgres `(healthy)`:

| Service | Purpose |
| --- | --- |
| `postgres` | Users, portfolios, bots, models registry, notifications, audit |
| `mongodb` | OHLCV candle history |
| `redis` | Market cache, rate limiting, sessions |
| `backend` | FastAPI on http://localhost:8000 |
| `market-ingestion` | Pulls top-50 prices + candle history every cycle |
| `trading-worker` | Runs paper / testnet bots |
| `notification-worker` | Sends queued emails (if SMTP configured) |
| `frontend` | React app on http://localhost:5173 |

### Checks

```powershell
curl http://localhost:8000/api/v1/health
# {"status":"ok","service":"AI Crypto Trading Platform","environment":"development"}
```

> The database commands below work in PowerShell, Git Bash and macOS/Linux shells. They use the default
> `POSTGRES_USER=crypto_user` and `POSTGRES_DB=crypto_trading` — substitute your values if you changed them in `.env`.
> Avoid `sh -c '... "$POSTGRES_USER" ...'` forms in Windows PowerShell 5.1: it strips the inner quotes and psql prints only `--`.

Confirm all migrations ran (27 tables, incl. `admin_audit`, `verification_email_outbox`):

```powershell
docker compose exec -T postgres psql -U crypto_user -d crypto_trading -c "\dt"
```

Wait for market history (needed for AI + bots). Each coin needs ~500 `1d` candles:

```powershell
docker compose logs -f market-ingestion          # look for "History cycle persisted N candle updates"
docker compose exec -T mongodb mongosh crypto_market --quiet --eval "db.market_data.countDocuments({symbol:'BTC',interval:'1d'})"
```

> Fresh-volume note: SQL files in `database/postgres/` run automatically only on a **new** volume. For an old volume, apply missing migrations in order (see README), or reset with `docker compose down -v` (deletes local data).

---

## B. Train the AI models

Bots, forecasts and ranking need an **active** model for **each symbol and interval** separately. A `1d` model does not answer `1h` requests — train every interval you want to show in the **AI predictions** screen or use in a bot.

Each command takes about **1–3 minutes**. All 8 below take roughly **15–20 minutes**. Run them one by one, or skip intervals you do not need.

### 1 hour (`1h`) — predicts the next hour

```powershell
docker compose --profile training run --rm prediction-trainer --symbol BTC --interval 1h --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
docker compose --profile training run --rm prediction-trainer --symbol ETH --interval 1h --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
```

### 4 hours (`4h`) — predicts the next 4 hours

```powershell
docker compose --profile training run --rm prediction-trainer --symbol BTC --interval 4h --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
docker compose --profile training run --rm prediction-trainer --symbol ETH --interval 4h --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
```

### 1 day (`1d`) — predicts the next day

```powershell
docker compose --profile training run --rm prediction-trainer --symbol BTC --interval 1d --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
docker compose --profile training run --rm prediction-trainer --symbol ETH --interval 1d --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
```

### 1 week (`1w`) — predicts the next week

```powershell
docker compose --profile training run --rm prediction-trainer --symbol BTC --interval 1w --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
docker compose --profile training run --rm prediction-trainer --symbol ETH --interval 1w --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate
```

### 1 month (`1M`) — not trainable

Training needs roughly **300+ continuous candles** after indicator warm-up. Binance only has about **112 monthly** BTC/ETH candles, so `1M` training fails with *DataError: At least 200 supervised sequences are required; ingest at least 300 candles*. The `1M` interval still works for charts and indicators in the **Market data** tab; the AI predictions screen shows *no active model* for it.

### Data needed per interval

| Interval | Stored candles (BTC, approx.) | Trainable |
| --- | --- | --- |
| `1h` | ~1000 | ✅ |
| `4h` | ~660 | ✅ |
| `1d` | ~527 | ✅ |
| `1w` | ~483 | ✅ |
| `1M` | ~112 | ❌ |

Check your own counts before training:

```powershell
docker compose exec -T mongodb mongosh crypto_market --quiet --eval "db.market_data.aggregate([{`$match:{symbol:{`$in:['BTC','ETH']}}},{`$group:{_id:{s:'`$symbol',i:'`$interval'},n:{`$sum:1}}},{`$sort:{'_id.s':1,'_id.i':1}}]).forEach(x=>print(x._id.s,x._id.i,x.n))"
```

(The backticks before `$` stop PowerShell from treating `$match`, `$sum` etc. as its own variables.)

### Output and confirmation

Each run prints JSON with the version UUID, validation/test metrics (MAE, RMSE, directional accuracy, F1), the persistence baseline and a held-out backtest. Confirm the active models:

```powershell
docker compose exec -T postgres psql -U crypto_user -d crypto_trading -c "select symbol, timeframe, model_id, is_active from ml_models where is_active order by symbol, timeframe"
```

Expected — exactly **one active row per symbol/interval** (8 rows; your `model_id` values will differ):

| symbol | timeframe | is_active |
| --- | --- | --- |
| BTC | 1d | t |
| BTC | 1h | t |
| BTC | 1w | t |
| BTC | 4h | t |
| ETH | 1d | t |
| ETH | 1h | t |
| ETH | 1w | t |
| ETH | 4h | t |

Every retrain with `--activate` adds a new row and switches the previous version for that symbol/interval to `f` (kept for rollback). To see all versions, drop `where is_active` from the query.

### Notes

- **Retrain short intervals more often.** `1h` and `4h` models go stale quickly — retrain them daily or weekly; `1d` / `1w` less often. The *Feature drift* badge on the AI predictions screen shows `review` when a model needs attention.
- **`At least 200 supervised sequences are required`:** ingestion has not finished for that interval — wait for `History cycle persisted …` in `docker compose logs -f market-ingestion` and retry. For more `4h` / `1d` history set `MARKET_HISTORY_CANDLE_LIMIT=1000` in `.env` and run `docker compose up -d market-ingestion`.
- **Other coins:** replace `BTC` / `ETH` with any top-50 symbol that has a Binance USDT pair (e.g. `SOL`, `BNB`, `XRP`).
- Omit `--activate` to create an inactive candidate and activate later with `--activate-version <UUID>`.

---

## C. Automated end-to-end test

[`scripts/e2e_demo.py`](../scripts/e2e_demo.py) exercises every module through the real API, inside the backend container:

```bash
docker compose exec -T backend python - < scripts/e2e_demo.py
```

PowerShell (no `<` redirect):

```powershell
Get-Content scripts/e2e_demo.py -Raw | docker compose exec -T backend python -
```

Each run creates a fresh trader `demo_<timestamp>@example.com` and reuses a stable admin **`demo.admin@example.com` / `StrongPass123!`** (promoted with the bootstrap CLI on the first run, if no admin exists yet). Exit code `0` = all checks passed.

### What it checks and the expected results

| # | Module | Checks | Expected |
| --- | --- | --- | --- |
| 1 | Health | `GET /health` | `ok` |
| 2 | Market data | Top-50, single asset, OHLCV for `1h 4h 1d 1w 1M`, stored history, indicators | 50 assets; 100 candles per interval; 500 stored `1d` candles |
| 3 | Auth | Register → login blocked (403) → verify → login → `/me` → refresh rotation (old token 401) → wrong password 401 → 2FA enable / login needs code / disable | All pass |
| 4 | Admin bootstrap | Register/verify `demo.admin@example.com`, run `app.admin.bootstrap` | Role `admin` |
| 5 | Portfolio & risk | 1000 USD → buy 2 @100 fee 2 → fill → sell 1 @120 fee 1 → cancel → max positions 1 → ETH buy | Available 798 / reserved 202; cash 917; **realized P&L 18**; ETH rejected: *Maximum open positions reached*; 2 fills |
| 6 | AI prediction | Model registry, BTC forecast, BTC+ETH ranking | Forecast with direction, price, confidence; both coins ranked |
| 7 | Exchanges | Capabilities, save encrypted Binance testnet connection, verify, balances, price, trades | *Connection verified. Read-only access is active.* (skipped if no testnet keys) |
| 8 | Trading bots | Create + start paper bot, decision history, stop; create testnet bot | `running` → decision (e.g. `hold / no_position`) → `stopped` |
| 9 | Notifications | Price alert, list, email preferences, inbox, CSV + PDF report | Alert created; inbox has `trade_executed` events; CSV + PDF bytes returned |
| 10 | Admin | Trader gets 403; overview, users, audit, operations, health check, model drift check | All pass; health lists postgres/mongo/redis reachable |
| 11 | Logout | Logout then refresh | Refresh token revoked (401) |

Final line on success:

```text
RESULT: 57/57 passed   demo login: demo_<timestamp>@example.com / StrongPass123!
```

---

## D. Unit test suites

Backend tests are not copied into the runtime image, so mount the source. Use CI settings (`APP_ENV=test`, rate limiting off) — otherwise the live `development` env triggers 429s in the auth tests.

```bash
MSYS_NO_PATHCONV=1 docker compose run --rm --no-deps -T \
  -e APP_ENV=test -e RATE_LIMIT_ENABLED=false \
  -v "$(pwd -W)/backend:/src" -v "$(pwd -W)/database:/database" -w /src \
  --entrypoint sh backend -c 'pip install -q pytest && python -m pytest -q'
```

(`$(pwd -W)` and `MSYS_NO_PATHCONV` are for Git Bash on Windows; on macOS/Linux use `$(pwd)` and drop the prefix.)
Expected: `165 passed, 17 skipped`. The skipped tests need a disposable `PREDICTION_TEST_DSN` / `REDIS_TEST_URL` database, as provided in CI.

Frontend:

```powershell
cd frontend
npm ci
npx vitest run          # 6 files, 16 tests passed
```

---

## E. Live browser demo script

Open **http://localhost:5173**. Keep **http://localhost:8000/docs** (Swagger) open in a second tab.
Before presenting: run parts A–C once so models exist and `demo.admin@example.com` is admin.

### 1. Market data — *no login*
Tab **Market data**.
- [ ] Top-50 table loads, updates live every 30 s (WebSocket).
- [ ] Select BTC → candlestick chart. Switch `1h / 4h / 1d / 1w / 1M`.
- [ ] Toggle SMA, EMA, Bollinger Bands, RSI, MACD, volume.

### 2. Registration, verification, login
Tab **Portfolio & risk**.
- [ ] **Create account** (e.g. `presenter` / `presenter@example.com` / `StrongPass123!`).
- [ ] In development the verification token is shown on screen → confirm it. *(Production emails it instead.)*
- [ ] Sign in. Point out: wrong password is rejected; 5 failures lock the account for 15 min.
- [ ] Optional 2FA: Swagger → **Authorize** with your access token → `POST /auth/2fa/setup` → add the secret to an authenticator app → `POST /auth/2fa/enable` → next login asks for the 6-digit code.

### 3. Paper portfolio & risk
Section **Portfolio**.
- [ ] Create portfolio with **1,000** virtual USD.
- [ ] Reserve **BTC buy**, qty **2**, price **100**, fee **2** → available cash **798**, reserved **202**.
- [ ] **Fill paper trade** → holding 2 BTC, cost basis 202, average cost 101.
- [ ] Reserve + fill **BTC sell**, qty **1**, price **120**, fee **1** → cash **917**, realized P&L **18**.
- [ ] Risk settings → **Max open positions = 1** → try an ETH buy → rejected *Maximum open positions reached*.
- [ ] Reserve a BTC sell and **cancel** it → quantity released. Show **Trade history**.

### 4. AI predictions
Swagger, authorized:
- [ ] `GET /api/v1/predictions/BTC?interval=1d` → direction, predicted price, confidence, model version.
- [ ] `GET /api/v1/predictions/models/BTC` → version registry.
- [ ] `POST /api/v1/predictions/opportunities` body `{"symbols":["BTC","ETH"],"interval":"1d"}` → ranked list.
- [ ] Mention: RF / XGBoost / LSTM ensemble, 70/15/15 time split, baseline comparison; educational, not financial advice.

### 5. Exchange connections
Section **Exchanges**.
- [ ] Add **Binance**, **Sandbox/testnet** on, paste testnet API key + secret → save (encrypted with AES; never returned).
- [ ] **Verify** → *Connection verified. Read-only access is active.*
- [ ] Show balances, BTC/USDT price, recent trades. Production connections are read-only by design.

### 6. Trading bots
Section **Bots**.
- [ ] New bot: mode **Paper USD**, your portfolio, pair **BTC/USD**, interval **1d**, confidence **0.5–0.7**, tick **Enable** → save → **Start** → state `running`.
- [ ] Watch `docker compose logs -f trading-worker`; open **History** → decision such as `hold / no_position` or a buy when the model is confident enough.
- [ ] **Stop**, **Close position**.
- [ ] Optional: a **Binance Spot Testnet** bot on the connection from step 5 (pair **BTC/USDT**) places real testnet orders.

### 7. Notifications, alerts & reports
Section **Notifications**.
- [ ] Create price alert: BTC **above** a value just below the current price → appears in the inbox in real time (WebSocket) on the next ingestion cycle.
- [ ] Inbox shows `trade_executed` events from step 3; mark as read.
- [ ] Download the trade report as **CSV** and **PDF**.
- [ ] Email toggle: delivery shows *not configured* unless SMTP/SendGrid variables are set.

### 8. Admin
Sign out → sign in as **demo.admin@example.com / StrongPass123!** → section **Admin**.
- [ ] Overview: user counts, running bots, worker heartbeat.
- [ ] Users: change a role / deactivate a user (recorded in **Audit**).
- [ ] **Run health check** → postgres / mongo / redis reachable with latency.
- [ ] Models → **Check** → healthy + feature-drift report.
- [ ] Show that a normal trader gets **403** on admin routes.

To make your own account admin instead: from the admin workspace set its role to `admin`, or (only when no admin exists yet)
`docker compose exec backend python -m app.admin.bootstrap --email you@example.com`, then sign in again.

---

## F. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `/market/assets` occasionally 502; logs show CoinGecko `429 Too Many Requests` | CoinGecko free-tier rate limit (shared by backend, ingestion and worker) | Transient — next 30 s cycle recovers. Close extra browser tabs; raise `MARKET_REFRESH_SECONDS` if frequent. |
| Inbox shows a `bot-failure` notification; worker log `Bot tick failed` | Same CoinGecko 429 during a bot tick | Next tick retries automatically. |
| Ingestion log `Binance OHLCV request failed for BUIDL` (or other tokens) | Asset has no Binance USDT pair | Harmless; skipped. |
| Training: not enough samples | History still backfilling | Wait for `History cycle persisted …`, retry. |
| Forecast / bot: *Prediction unavailable* | No active model for that symbol/interval | Train with `--activate` (Part B). |
| Bootstrap: *An active administrator already exists* | Bootstrap only creates the first admin | Use the admin workspace to promote users. |
| Backend pytest auth tests fail with 429 | Run with container's `development` env | Add `-e APP_ENV=test -e RATE_LIMIT_ENABLED=false` (Part D). |
| A `psql` check prints only `--` / `(1 row)` | PowerShell 5.1 stripped the inner quotes of a `sh -c '…"$VAR"…'` command | Use the direct form: `docker compose exec -T postgres psql -U crypto_user -d crypto_trading -c "…"` |
| `docker: failed to connect to the docker API` | Docker Desktop not running | Start Docker Desktop, wait for "Engine running". |
| Exchange verify fails | Wrong / mainnet keys | Use keys from testnet.binance.vision with sandbox on. |

Useful commands:

```powershell
docker compose ps
docker compose logs -f backend market-ingestion trading-worker notification-worker
docker compose restart backend
docker compose exec postgres psql -U crypto_user -d crypto_trading      # interactive SQL shell
docker compose down          # stop, keep data
docker compose down -v       # stop and DELETE all local data
```
