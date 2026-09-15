# Phase 6 — Exchange connections

## Delivered behavior and boundaries

The account workspace now includes **Exchange connections** for Binance, Coinbase Advanced Trade and Kraken. It verifies credentials before storing them and supports replacement, removal, balances, prices, existing order status and recent trade queries. CCXT is pinned to 4.5.78; its required cryptography dependency is constrained to 50.x and validated with the existing auth/encryption suite.

Every persisted connection is read-only, enforced by the database and service policy. No HTTP exchange order placement or cancellation routes exist. Internal adapter methods implement the planned operations, but require a supported sandbox and explicit mutation permission; placement also requires a portfolio risk validator. Tests exercise the Phase 5 risk validator through this boundary. The Phase 7 engine must supply atomic reservations, durable reconciliation and order lifecycle before exposing exchange submission. Exchange balances never alter virtual paper portfolios.

## Provider capabilities

| Exchange | Production | Sandbox in this adapter |
| --- | --- | --- |
| Binance | Spot account reads | Spot testnet, selected before any network call |
| Coinbase Advanced Trade | Spot account reads | Unsupported; static responses are not an execution simulator |
| Kraken | Spot account reads | Unsupported; separately provisioned spot UAT is not configured |

Capability references reviewed for this implementation:

- [CCXT manual](https://github.com/ccxt/ccxt/wiki/manual): sandbox mode must be selected immediately after construction, before other calls.
- [Binance spot testnet](https://developers.binance.com/en/docs/products/spot/testnet/general-info): separate endpoints and virtual assets; resets can remove test history.
- [Coinbase sandbox](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/sandbox): predefined static account/order responses.
- [Kraken exchange overview](https://docs.kraken.com/exchange/guides/overview): spot UAT access via Account Manager; derivatives demo is not a spot testnet.

Unsupported sandbox selection fails before transport construction. No production fallback or user-supplied remote URL is accepted. Provider permissions and availability still determine whether account reads succeed.

## Upgrade an existing deployment

Keep existing volumes. Apply the additive, rerunnable migration after the earlier migrations:

```bash
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/postgres/005_exchange.sql
```

Generate a dedicated 32-byte key privately:

```bash
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Put its base64 value in `EXCHANGE_ENCRYPTION_KEY` in the untracked environment/secret configuration, then rebuild:

```bash
docker compose up -d --build
```

Fresh volumes initialize SQL automatically. A missing/malformed exchange key returns a safe 503 only on operations requiring encryption/decryption; the rest of the platform still starts. Never reuse the JWT or auth-encryption key, commit secrets, or delete volumes as an upgrade strategy.

## Frontend walkthrough

1. Open the frontend (default port 5173), select **Portfolio & risk**, and sign in.
2. Choose **Exchange connections** in the account workspace.
3. Select the exchange/environment and label. Use account-read-only keys, with trading/withdrawals disabled. Binance testnet needs separate keys. Coinbase uses its issued key name and EC private key; preserve PEM line breaks.
4. Choose **Verify and save connection**. Verification must succeed before persistence. Inputs clear after saving and stored secrets are never returned.
5. Inspect available, used and total balances for the selected account.
6. Query a unified spot symbol, such as BTC/USDT for Binance or BTC/USD for Coinbase/Kraken. Choose an optional UTC start time and result limit for recent trades.
7. Look up an existing order by exchange order ID and symbol.
8. Replace credentials using the replacement form; failed verification keeps the prior ciphertext.
9. Remove the local connection when no longer needed. This does not revoke its key at the exchange.

Authentication remains memory-only; exchange credentials are not written to browser storage. Query caches are isolated per mounted authenticated workspace. The connection form prevents an older list response from hiding a newly saved record.

## API

All paths are beneath `/api/v1/exchanges` and require bearer authentication.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/capabilities` | Supported exchanges/environments and limitations |
| GET / POST | root | List owned metadata / verify and create connection |
| PUT | `/{id}/credentials` | Verify and replace credentials |
| DELETE | `/{id}` | Delete owned local connection |
| POST | `/{id}/verify` | Authenticated account-read probe |
| GET | `/{id}/balances` | Decimal available/used/total balances |
| GET | `/{id}/price?symbol=BTC/USD` | Last price and observation timestamp |
| GET | `/{id}/orders/{order_id}?symbol=BTC/USD` | Normalized order state |
| GET | `/{id}/trades?symbol=BTC/USD&since=2026-01-01T00:00:00Z&limit=50` | Bounded private trade query, limit 1–100 |

Create bodies contain `exchange`, `label`, `sandbox`, and `credentials` (`api_key`, `api_secret`, optional `passphrase`). Replacement bodies contain only credential fields. One connection per owner/exchange/environment; duplicates return 409 and cross-owner access returns 404. Default request validation is sanitized so it does not echo raw credential input. Provider credential rejection is 422, missing permission 403, rate limits 429, timeouts/network failures 503, malformed provider data 502. Safe errors never include raw provider payloads.

Trade queries forward `since`/`limit` to CCXT, deduplicate returned IDs and sort by time. Retention and ordering differ by exchange. A full response sets `possibly_truncated`; this is not a complete archive or a portable pagination cursor. Phase 7 reconciliation and Phase 8 exports require durable ingestion and provider-specific cursors. Prices without provider timestamps use receipt time and are reference quotes, not execution guarantees. Missing numeric balances are not fabricated as zero.

## Key rotation

AES-256-GCM uses a random nonce and authenticated context binding ciphertext to owner, exchange and connection UUID. Moving ciphertext to another identity fails authentication. Only the backend decrypts credentials for a fixed-provider client; public metadata excludes both credentials and ciphertext.

1. Back up the database and old key securely; stop backend and any other credential writers.
2. Supply `EXCHANGE_OLD_ENCRYPTION_KEY` and `EXCHANGE_NEW_ENCRYPTION_KEY` privately to a one-off backend process. Do not put values in command arguments or source files.
3. Run `python -m app.exchange.rotate_key` with PostgreSQL accessible. All rows are locked and re-encrypted in one transaction; failure rolls back the whole operation.
4. After success, configure `EXCHANGE_ENCRYPTION_KEY` with the new key on all instances before restarting writers.
5. Verify read access. Retain old keys only as required for encrypted backups, then retire them.

Do not simply change the key without re-encryption: existing records become unreadable. Rotation logs only a count or a safe error.

## Validation

Unit tests mock network calls and validate real pinned CCXT constructors without contacting exchanges. PostgreSQL CI tests cover migration reruns, ownership, encrypted persistence, failed replacement and atomic key rotation. Frontend tests exercise credentials, environments, failure states, balances and order/trade inspection. Local and CI results are recorded in the checklist/PR. No real exchange keys, live orders or live-provider smoke tests are used; deployment smoke checks require separately supplied read-only/testnet credentials.
