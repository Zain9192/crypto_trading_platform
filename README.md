# AI Crypto Trading Platform

## Requirements

- Docker Desktop, running
- Git
- A Bash terminal for the commands below (on Windows, use Git Bash, not Command Prompt)
- Internet access to `api.binance.com` and `api.coingecko.com`

## 1. Get the code

```bash
git clone https://github.com/Zain9192/crypto_trading_platform.git
cd crypto_trading_platform
```

## 2. Create the environment file

```bash
cp .env.example .env
```

Generate three secrets:

```bash
docker run --rm python:3.12-slim python -c "import secrets,base64,os; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48)); print('AUTH_DATA_ENCRYPTION_KEY=' + base64.urlsafe_b64encode(os.urandom(32)).decode()); print('EXCHANGE_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

In `.env`:

1. Replace the `JWT_SECRET_KEY`, `AUTH_DATA_ENCRYPTION_KEY` and `EXCHANGE_ENCRYPTION_KEY` lines with the three printed lines.
2. Set `POSTGRES_PASSWORD` to any password.
3. Set `MARKET_HISTORY_CANDLE_LIMIT=1000`.
4. Leave `APP_ENV=development`.

## 3. Start the app

```bash
docker compose up -d --build
docker compose ps
```

All eight services should show `running`. The first build takes several minutes.

| What | URL |
|---|---|
| App | http://localhost:5173 |
| API (interactive) | http://localhost:8000/docs |

## 4. Wait for market history

Ingestion starts automatically. Check how many BTC candles are stored:

```bash
docker compose exec mongodb mongosh --quiet crypto_market --eval 'for (const i of ["1h","4h","1d"]) print(i, db.market_data.countDocuments({symbol:"BTC", interval:i}))'
```

Continue when `1h`, `4h` and `1d` each show `1000`, usually within a few minutes.

## 5. Train a model

```bash
docker compose --profile training run --rm prediction-trainer --symbol BTC --interval 1h --limit 1000 --activate
```

The trainer prints its results as JSON. To compare the model with simple baselines:

| Field | Meaning |
|---|---|
| `metrics.test.ensemble.accuracy` | Share of held-out candles where the direction was right. 0.5 is a coin flip. |
| `metrics.test.ensemble.mae` vs `baseline_mae` | Price error vs. assuming the price stays the same. Lower is better. |
| `backtest.total_return` vs `buy_hold_return` | Strategy return vs. simply holding the coin over the same period. |

To train another coin or interval, change `--symbol` and `--interval`. Only `--activate`d models serve predictions.

## 6. See the results

### Create an account

1. Open http://localhost:5173 and choose **Portfolio & risk**.
2. Choose **Create account** and register. The development verification token is filled in for you; choose **Verify email**, then sign in.

### Paper trade

1. In **Paper portfolio**, choose **Create paper portfolio**.
2. Under **New paper trade**, enter a BTC buy and choose **Reserve paper trade**.
3. Under **Pending paper trades**, choose **Fill paper trade**.
4. Cash, **Holdings & allocation**, P&L and **Trade history** update.

### Prediction-driven bot

1. In **Trading bots**, create a paper bot with symbol `BTC/USD`, interval `1h`, minimum confidence `0.5` and an order amount such as `0.001` (BTC), then choose **Save bot**.
2. Choose **Start**. Under **Decisions and fills**, the bot records one decision per closed hourly candle: `buy`, `sell` or `hold`, with the reason. Buys also appear in the portfolio's **Trade history**.

### Live forecast

1. Open http://localhost:8000/docs.
2. Run `POST /api/v1/auth/login` with your email and password, and copy `access_token` from the response.
3. Choose **Authorize**, paste the token, and confirm.
4. Run `GET /api/v1/predictions/{symbol}` with `symbol` = `BTC` and `interval` = `1h`.

The response shows the current price, predicted price, `direction` (`up`, `down`, or `neutral` when the models disagree), confidence and expected return.

### Model metrics in the app (optional)

Make your account an administrator, then sign in again:

```bash
docker compose exec backend python -m app.admin.bootstrap --email you@example.com
```

**Administration → Model registry** lists each trained model with its metrics and backtest, and **Check prediction** runs the active model.

## Stop the app

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and delete all data, history and models
```
