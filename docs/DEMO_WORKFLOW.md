# Demo & End-to-End Test Workflow

A step-by-step guide to start the platform, verify every module automatically, and present each module live in the browser.

Verified on 2026-11-14 (Windows 11, Docker Desktop, Compose v5): **57/57 end-to-end checks, 165 backend tests, 16 frontend tests passing.**

| Part | What it covers | Time |
| --- | --- | --- |
| [A. Start the stack](#a-start-the-stack) | Docker services, migrations, market history | 5–15 min (first time) |
| [B. Train AI models](#b-train-the-ai-models) | 20 coins × `1h`, `4h`, `1d`, `1w` (80 models) in one loop | 15–40 min |
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

Wait for market history (needed for AI + bots). Each coin needs **300+** `1d` candles to train (a full backfill stores ~500):

```powershell
docker compose logs -f market-ingestion          # look for "History cycle persisted N candle updates"
docker compose exec -T mongodb mongosh crypto_market --quiet --eval "const coins=['BTC','ETH','BNB','XRP','SOL','TRX','ZEC','DOGE','LINK','ADA','XLM','NEAR','BCH','LTC','AVAX','UNI','HBAR','AAVE','PAXG','USDC']; let ok=0; coins.forEach(s=>{ const n=db.market_data.countDocuments({symbol:s,interval:'1d'}); if(n>=300) ok++; print(s.padEnd(5), String(n).padStart(5), n>=300?'OK':'LOW'); }); print('1d history ready: '+ok+' / '+coins.length);"
```

Expected — one line per coin, ending with `1d history ready: 20 / 20`. Any `LOW` means ingestion is still backfilling that coin; wait a few minutes and rerun. For all four intervals (`1h`, `4h`, `1d`, `1w`) use the check in [Part B → Step 1](#step-1--check-all-20-coins-are-ingested).

> Fresh-volume note: SQL files in `database/postgres/` run automatically only on a **new** volume. For an old volume, apply missing migrations in order (see README), or reset with `docker compose down -v` (deletes local data).

---

## B. Train the AI models

Forecasts, the **AI predictions** screen, opportunity ranking and bots need an **active model for each coin and interval** — a `1d` model does not answer `1h` requests. This part trains **20 coins × 4 intervals = 80 models** with one loop.

**Coins:** `BTC ETH BNB XRP SOL TRX ZEC DOGE LINK ADA XLM NEAR BCH LTC AVAX UNI HBAR AAVE PAXG USDC`
**Intervals:** `1h` (predicts the next hour), `4h` (next 4 hours), `1d` (next day), `1w` (next week)

> - These are the top-50 coins with a Binance USDT pair and enough history on all four intervals.
> - `USDC` is a stablecoin (≈ $1) and `PAXG` tracks gold, so their forecasts are of little trading use; remove them from `$coins` below if you only want volatile coins.
> - **`USDC 1w` cannot be trained**: Binance has no USDC trading from Sept 2022 to March 2023, leaving too few continuous weekly candles. Expect **79 / 80** models.
> - **`1M` (monthly) cannot be trained** for any coin: only ~112 monthly candles exist and training needs ~300. `1M` still works for charts in the **Market data** tab.

### Step 1 — Check all 20 coins are ingested

Training reads the **latest 1000 candles** and needs **300+ continuous candles** (no gaps). This command checks exactly that for all 80 coin/interval pairs:

```powershell
docker compose exec -T mongodb mongosh crypto_market --quiet --eval "const coins=['BTC','ETH','BNB','XRP','SOL','TRX','ZEC','DOGE','LINK','ADA','XLM','NEAR','BCH','LTC','AVAX','UNI','HBAR','AAVE','PAXG','USDC']; const ivs={'1h':36e5,'4h':144e5,'1d':864e5,'1w':6048e5}; let ok=0; coins.forEach(s=>{ print(s.padEnd(5), Object.keys(ivs).map(i=>{ const t=db.market_data.find({symbol:s,interval:i},{timestamp:1,_id:0}).sort({timestamp:-1}).limit(1000).toArray().map(x=>+x.timestamp); let g=0; for(let k=1;k<t.length;k++){ if(t[k-1]-t[k]!==ivs[i]) g++; } const st=t.length<300?'LOW ':(g?'GAPS':'OK  '); if(st==='OK  ') ok++; return (i+'='+t.length).padEnd(8)+' '+st; }).join('  ')); }); print('Ready to train: '+ok+' / 80   (OK = 300+ candles and no gaps in the latest 1000)');"
```

Expected when ready:

```text
BTC   1h=1000  OK    4h=684   OK    1d=531   OK    1w=484   OK
ETH   1h=1000  OK    4h=684   OK    1d=531   OK    1w=484   OK
...
USDC  1h=1000  OK    4h=684   OK    1d=531   OK    1w=393   GAPS
Ready to train: 79 / 80   (OK = 300+ candles and no gaps in the latest 1000)
```

| Status | Meaning | Fix |
| --- | --- | --- |
| `OK` | 300+ continuous candles | Ready |
| `LOW` | Ingestion is still backfilling (fresh setup: 10–20 min) | Wait for `History cycle persisted …` in `docker compose logs -f market-ingestion`, rerun the check |
| `GAPS` on `1h` | The stack was off for more than ~3 weeks, and ingestion only re-fetches the latest `MARKET_HISTORY_CANDLE_LIMIT` (500) candles, so the hole is never refilled | Set `MARKET_HISTORY_CANDLE_LIMIT=1000` in `.env`, run `docker compose up -d market-ingestion`, wait for the next `History cycle persisted …` (~15–20 min), rerun the check |
| `GAPS` on `USDC 1w` | Gap in Binance's own data | Cannot be fixed — that one model will fail |

### Step 2 — Train all 80 models

Paste the whole block into PowerShell from the project folder. It trains every coin on every interval, activates each model, saves each run's output to a log file and lists any failures at the end:

```powershell
$coins = "BTC","ETH","BNB","XRP","SOL","TRX","ZEC","DOGE","LINK","ADA","XLM","NEAR","BCH","LTC","AVAX","UNI","HBAR","AAVE","PAXG","USDC"
$intervals = "1h","4h","1d","1w"
$logs = "$env:USERPROFILE\crypto-training-logs"; New-Item -ItemType Directory -Force $logs | Out-Null
$failed = @()
foreach ($s in $coins) { foreach ($i in $intervals) {
  Write-Host "Training $s $i ..."
  docker compose --profile training run --rm prediction-trainer --symbol $s --interval $i --limit 1000 --lookback 20 --epochs 10 --trees 100 --activate *> "$logs\$s-$i.log"
  if ($LASTEXITCODE -ne 0) { $failed += "$s $i"; Write-Host "  FAILED - see $logs\$s-$i.log" } else { Write-Host "  done" }
} }
if ($failed) { "Failed: $($failed -join ', ')" } else { "All models trained and activated." }
```

- **Time:** about **8 seconds to 1 minute per model** → roughly **15–40 minutes** for all 80. Keep the laptop awake.
- **Expected result:** `Failed: USDC 1w` (see above). Anything else in the failed list → open its log.
- **Logs:** `C:\Users\<you>\crypto-training-logs\<COIN>-<interval>.log` — metrics and backtest on success, the error on failure. The most common error, `Stored candles contain duplicates or gaps`, means Step 1 showed `GAPS`.
- **Retry only failures:** set `$coins` and `$intervals` to the failed ones and paste the block again. Retraining is safe — each successful run activates a new version and keeps the old one for rollback.

### Step 3 — Check all 80 models are trained

```powershell
docker compose exec -T postgres psql -U crypto_user -d crypto_trading -c "with c(symbol) as (values ('BTC'),('ETH'),('BNB'),('XRP'),('SOL'),('TRX'),('ZEC'),('DOGE'),('LINK'),('ADA'),('XLM'),('NEAR'),('BCH'),('LTC'),('AVAX'),('UNI'),('HBAR'),('AAVE'),('PAXG'),('USDC')), i(tf) as (values ('1h'),('4h'),('1d'),('1w')), want as (select symbol, tf from c cross join i) select count(*) filter (where m.symbol is not null) as trained, count(*) as expected, coalesce(string_agg(w.symbol || ' ' || w.tf, ', ' order by w.symbol, w.tf) filter (where m.symbol is null), 'none') as missing from want w left join ml_models m on m.is_active and m.symbol = w.symbol and m.timeframe = w.tf"
```

Expected:

```text
 trained | expected | missing
---------+----------+---------
      79 |       80 | USDC 1w
```

`missing` lists every coin/interval without an active model — retrain just those with the Step 2 loop. Then open **AI predictions** in the app, pick a coin and interval, and use **Opportunity ranking** (up to 20 coins at a time).

### Notes

- **Retrain short intervals more often.** `1h` / `4h` models go stale quickly — retrain them daily or weekly; `1d` / `1w` less often. The *Feature drift* badge on the AI predictions screen shows `review` when a model needs attention.
- **Other coins:** any top-50 coin with a Binance USDT pair and a clean Step 1 check can be added to `$coins` (e.g. `SUI`, `TAO`, `SHIB` on `1h`/`4h`/`1d`).
- **All versions:** `docker compose exec -T postgres psql -U crypto_user -d crypto_trading -c "select symbol, timeframe, model_id, is_active, trained_at from ml_models order by symbol, timeframe, trained_at"`.
- **Inactive candidates:** remove `--activate` to train without switching the live model, then activate later with `docker compose --profile training run --rm prediction-trainer --activate-version <UUID>`.

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
| Training: *At least 200 supervised sequences are required* | History still backfilling (`LOW` in Part B Step 1) | Wait for `History cycle persisted …`, retry. |
| Training: *Stored candles contain duplicates or gaps* (usually all `1h`) | Stack was off for weeks; ingestion only re-fetches the latest 500 candles (`GAPS` in Part B Step 1) | Set `MARKET_HISTORY_CANDLE_LIMIT=1000` in `.env`, `docker compose up -d market-ingestion`, wait one history cycle, retrain `1h`. |
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
