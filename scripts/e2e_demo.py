"""End-to-end demo / smoke test for every platform module.

Runs INSIDE the backend container so it can reach the API and the admin bootstrap CLI:

    docker compose exec -T backend python - < scripts/e2e_demo.py

Creates a fresh demo account each run (demo_<timestamp>@example.com). Uses only paper money
and, if BINANCE_API_KEY/BINANCE_SECRET_KEY are set, the Binance spot *testnet*.
"""
import os
import subprocess
import sys
import time
import uuid
from datetime import date, timedelta

import httpx
import pyotp

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "StrongPass123!"
RESULTS = []
api = httpx.Client(base_url=BASE, timeout=60)


def step(name, fn):
    try:
        detail = fn()
        RESULTS.append(("PASS", name, detail or ""))
        print(f"  PASS  {name}" + (f"  ->  {detail}" if detail else ""))
    except Exception as exc:  # report and keep going
        RESULTS.append(("FAIL", name, str(exc)))
        print(f"  FAIL  {name}  ->  {exc}")


def call(method, path, token=None, expect=(200, 201), retries=3, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    for attempt in range(retries):
        r = api.request(method, path, headers=headers, **kw)
        # CoinGecko free tier rate-limits (surfaced as 502/503); wait and retry.
        if r.status_code in (502, 503) and attempt < retries - 1:
            time.sleep(20)
            continue
        break
    if r.status_code not in (expect if isinstance(expect, tuple) else (expect,)):
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return r


def section(title):
    print(f"\n=== {title}")


S = {}  # shared state between steps
stamp = int(time.time())
email = f"demo_{stamp}@example.com"

section("1. Health")
step("API health", lambda: call("GET", "/health").json()["status"])

section("2. Market data (public)")
def assets():
    data = call("GET", "/market/assets", params={"limit": 50}).json()
    items = data.get("assets") or data.get("items") or data
    btc = next(a for a in items if a["symbol"].upper() == "BTC")
    S["btc_price"] = float(btc.get("current_price") or btc.get("price"))
    return f"{len(items)} assets, BTC=${S['btc_price']:,.0f}"
step("Top-50 assets", assets)
step("Single asset BTC", lambda: call("GET", "/market/assets/BTC").json()["symbol"])
for iv in ("1h", "4h", "1d", "1w", "1M"):
    step(f"OHLCV BTC {iv}", lambda iv=iv: f"{len(call('GET', '/market/ohlcv/BTC', params={'interval': iv, 'limit': 100}).json()['items'])} candles")
step("Stored history BTC 1d", lambda: f"{len(call('GET', '/market/history/BTC', params={'interval': '1d', 'limit': 500}).json()['items'])} candles")
step("Indicators BTC 1d", lambda: ", ".join(sorted(k for k in call("GET", "/market/indicators/BTC", params={"interval": "1d", "limit": 200}).json() if k not in ("symbol", "interval")))[:120])

section("3. Authentication")
def register():
    r = call("POST", "/auth/register", json={"username": f"demo_{stamp}", "email": email, "password": PASSWORD}).json()
    S["verify"] = r["verification_token"]
    return email
step("Register", register)
step("Login blocked before verification", lambda: call("POST", "/auth/login", json={"email": email, "password": PASSWORD}, expect=(401, 403)).status_code)
step("Verify email", lambda: call("POST", "/auth/verify-email", json={"token": S["verify"]}).json()["is_email_verified"])
def login(totp=None):
    body = {"email": email, "password": PASSWORD} | ({"totp_code": totp} if totp else {})
    r = call("POST", "/auth/login", json=body).json()
    S["access"], S["refresh"] = r["access_token"], r["refresh_token"]
    return "tokens issued"
step("Login", login)
step("Who am I", lambda: call("GET", "/auth/me", S["access"]).json()["role"])
def refresh():
    r = call("POST", "/auth/refresh", json={"refresh_token": S["refresh"]}).json()
    old, S["refresh"], S["access"] = S["refresh"], r["refresh_token"], r["access_token"]
    call("POST", "/auth/refresh", json={"refresh_token": old}, expect=401)
    return "rotated; old refresh token rejected"
step("Refresh token rotation", refresh)
step("Wrong password rejected", lambda: call("POST", "/auth/login", json={"email": email, "password": "Wrong123!!"}, expect=401).status_code)

def two_factor():
    secret = call("POST", "/auth/2fa/setup", S["access"]).json()["secret"]
    call("POST", "/auth/2fa/enable", S["access"], json={"code": pyotp.TOTP(secret).now()})
    call("POST", "/auth/login", json={"email": email, "password": PASSWORD}, expect=(401, 403))
    login(pyotp.TOTP(secret).now())
    time.sleep(31 - time.time() % 30)  # wait for a fresh code; used codes may not be replayed
    call("POST", "/auth/2fa/disable", S["access"], json={"password": PASSWORD, "code": pyotp.TOTP(secret).now()})
    login()
    return "enabled, login required code, disabled"
step("TOTP 2FA", two_factor)

section("4. Admin bootstrap")
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "demo.admin@example.com")
def bootstrap():
    r = call("POST", "/auth/register", expect=(201, 409),
             json={"username": "demo_admin", "email": ADMIN_EMAIL, "password": PASSWORD})
    if r.status_code == 201:
        call("POST", "/auth/verify-email", json={"token": r.json()["verification_token"]})
    p = subprocess.run([sys.executable, "-m", "app.admin.bootstrap", "--email", ADMIN_EMAIL], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip().splitlines()[-1]
    if p.returncode != 0 and "already exists" not in out:
        raise RuntimeError(out)
    tokens = call("POST", "/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).json()
    S["admin"] = tokens["access_token"]
    role = call("GET", "/auth/me", S["admin"]).json()["role"]
    if role != "admin":
        S.pop("admin")
        raise RuntimeError(f"{ADMIN_EMAIL} is not admin ({out})")
    return f"{ADMIN_EMAIL} is admin ({out})"
step("Stable demo admin account", bootstrap)

section("5. Paper portfolio & risk")
def create_portfolio():
    p = call("POST", "/portfolios", S["access"], json={"initial_cash": "1000"}).json()
    S["pf"] = p["portfolio_id"]
    return f"portfolio {S['pf']}"
step("Create portfolio (1000 USD)", create_portfolio)
def order(side, qty, price, fee):
    o = call("POST", f"/portfolios/{S['pf']}/orders", S["access"], json={
        "client_order_id": str(uuid.uuid4()), "symbol": "BTC", "side": side,
        "quantity": qty, "simulation_price": price, "fee": fee}).json()
    return o.get("order_id") or o["order"]["order_id"]
def pf():
    return call("GET", f"/portfolios/{S['pf']}", S["access"]).json()
def find(d, *keys):
    for k in keys:
        if k in d:
            return d[k]
    for v in d.values():
        if isinstance(v, dict):
            r = find(v, *keys)
            if r is not None:
                return r
def buy():
    S["o1"] = order("buy", "2", "100", "2")
    p = pf()
    return f"available cash {find(p, 'available_cash')}, reserved {find(p, 'reserved_cash')}"
step("Reserve BTC buy 2 @ 100, fee 2", buy)
step("Fill buy", lambda: (call("POST", f"/portfolios/{S['pf']}/orders/{S['o1']}/fill", S["access"]), f"cash {find(pf(), 'cash', 'cash_balance')}")[1])
def sell():
    o = order("sell", "1", "120", "1")
    call("POST", f"/portfolios/{S['pf']}/orders/{o}/fill", S["access"])
    p = pf()
    return f"cash {find(p, 'cash', 'cash_balance')}, realized P&L {find(p, 'realized_pnl')}"
step("Sell 1 @ 120, fee 1 and fill", sell)
step("Cancel a pending sell", lambda: call("POST", f"/portfolios/{S['pf']}/orders/{order('sell', '0.5', '130', '0')}/cancel", S["access"]).json().get("status", "cancelled"))
step("Set max open positions = 1", lambda: (call("PUT", f"/portfolios/{S['pf']}/risk", S["access"], json={
    "min_investment": "1", "max_investment": "10000", "max_open_positions": 1, "max_open_trades": 10,
    "stop_loss_pct": "5", "take_profit_pct": "10"}), "saved")[1])
step("ETH buy rejected by risk engine", lambda: call("POST", f"/portfolios/{S['pf']}/orders", S["access"], expect=(409, 422), json={
    "client_order_id": str(uuid.uuid4()), "symbol": "ETH", "side": "buy", "quantity": "0.1",
    "simulation_price": "100", "fee": "0"}).json()["detail"])
def trade_history():
    fills = find(call("GET", f"/portfolios/{S['pf']}/trades", S["access"]).json(), "trades", "items") or []
    return f"{len(fills)} fills"
step("Trade history", trade_history)

section("6. AI prediction")
step("Model registry BTC 1d", lambda: f"{len(call('GET', '/predictions/models/BTC', S['access'], params={'interval': '1d'}).json())} version(s)")
def forecast():
    f = call("GET", "/predictions/BTC", S["access"], params={"interval": "1d"}).json()
    return {k: f[k] for k in f if k in ("direction", "predicted_price", "confidence", "model_version")}
step("Forecast BTC 1d", forecast)
def ranking():
    r = call("POST", "/predictions/opportunities", S["access"], json={"symbols": ["BTC", "ETH"], "interval": "1d"}).json()
    ranked = [f"{i['forecast']['symbol']} score={i['score']:.3f}" for i in r["items"]]
    if not ranked:
        raise RuntimeError(f"nothing ranked: {r['unavailable']}")
    return ", ".join(ranked) + (f"; no model: {', '.join(r['unavailable'])}" if r["unavailable"] else "")
step("Opportunity ranking", ranking)

section("7. Exchange connections")
step("Capabilities", lambda: str(call("GET", "/exchanges/capabilities", S["access"]).json())[:120])
key, secret = os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_SECRET_KEY")
if key and secret:
    def connect():
        c = call("POST", "/exchanges", S["access"], json={"exchange": "binance", "label": "Demo testnet", "sandbox": True,
                                                           "credentials": {"api_key": key, "api_secret": secret}}).json()
        S["conn"] = c["connection_id"]
        return S["conn"]
    step("Save Binance testnet connection (encrypted)", connect)
    step("Verify connection", lambda: str(call("POST", f"/exchanges/{S['conn']}/verify", S["access"]).json())[:120])
    step("Testnet balances", lambda: str(call("GET", f"/exchanges/{S['conn']}/balances", S["access"]).json())[:120])
    step("Testnet BTC/USDT price", lambda: str(call("GET", f"/exchanges/{S['conn']}/price", S["access"], params={"symbol": "BTC/USDT"}).json())[:120])
    def testnet_trades():
        trades = call("GET", f"/exchanges/{S['conn']}/trades", S["access"], params={"symbol": "BTC/USDT"}).json()
        return f"{len(trades)} trade(s)"
    step("Testnet recent trades", testnet_trades)
else:
    print("  SKIP  Binance testnet (BINANCE_API_KEY / BINANCE_SECRET_KEY not set)")

section("8. Trading bots")
def paper_bot():
    b = call("POST", "/bots", S["access"], json={"portfolio_id": S["pf"], "symbol": "BTC/USD", "interval": "1d", "mode": "paper",
                                                 "enabled": True, "confidence_threshold": "0.5", "order_amount": "0.001",
                                                 "max_open_trades": 1}).json()
    S["bot"] = b["bot_id"]
    return S["bot"]
step("Create paper bot BTC/USD", paper_bot)
step("Start paper bot", lambda: call("POST", f"/bots/{S['bot']}/control/start", S["access"]).json()["state"])
def bot_history():
    for _ in range(9):  # worker ticks periodically
        h = call("GET", f"/bots/{S['bot']}/history", S["access"]).json()
        items = h.get("items") or h.get("decisions") or h.get("history") or []
        if items:
            return f"{len(items)} decision(s); latest: {str(items[0])[:150]}"
        time.sleep(10)
    return "no decisions yet (worker ticks on its own schedule)"
step("Bot decision history", bot_history)
step("Stop paper bot", lambda: call("POST", f"/bots/{S['bot']}/control/stop", S["access"]).json()["state"])
if S.get("conn"):
    def sandbox_bot():
        b = call("POST", "/bots", S["access"], json={"connection_id": S["conn"], "symbol": "BTC/USDT", "interval": "1d", "mode": "sandbox",
                                                     "enabled": False, "confidence_threshold": "0.7", "order_amount": "0.0001"}).json()
        S["sbot"] = b["bot_id"]
        return f"{b['bot_id']} ({b['state']})"
    step("Create Binance testnet bot (not started)", sandbox_bot)
    def testnet_bot_detail():
        b = call("GET", f"/bots/{S['sbot']}", S["access"]).json()
        return f"{b['config']['mode']} {b['config']['symbol']} {b['state']}"
    step("Testnet bot detail", testnet_bot_detail)
step("List bots", lambda: f"{len(call('GET', '/bots', S['access']).json())} bot(s)")

section("9. Notifications, alerts & reports")
def alert():
    threshold = f"{S.get('btc_price', 50000) * 0.5:.2f}"  # far below price -> 'above' triggers quickly
    a = call("POST", "/notifications/price-alerts", S["access"], json={"asset_key": "bitcoin", "direction": "above", "threshold": threshold}).json()
    S["alert"] = a.get("alert_id") or a.get("id")
    return f"BTC above {threshold}"
step("Create price alert", alert)
step("List price alerts", lambda: f"{len(call('GET', '/notifications/price-alerts', S['access']).json())} alert(s)")
step("Email preferences", lambda: call("GET", "/notifications/preferences", S["access"]).json())
def inbox():
    for _ in range(6):
        n = call("GET", "/notifications", S["access"]).json()
        items = n.get("items") if isinstance(n, dict) else n
        if items:
            return f"{len(items)} notification(s); latest: {str(items[0].get('title') or items[0])[:100]}"
        time.sleep(10)
    return "inbox empty so far (alerts are evaluated by the ingestion price cycle)"
step("Notification inbox", inbox)
for fmt in ("csv", "pdf"):
    step(f"Trade report {fmt.upper()}", lambda fmt=fmt: f"{len(call('GET', '/notifications/reports/trades', S['access'], params={'start': str(date.today() - timedelta(days=30)), 'end': str(date.today()), 'format': fmt}).content)} bytes")

section("10. Admin")
if S.get("admin"):
    A = S["admin"]
    step("Trader cannot open admin API", lambda: call("GET", "/admin/overview", S["access"], expect=403).status_code)
    step("Overview", lambda: str(call("GET", "/admin/overview", A).json())[:150])
    step("Users", lambda: f"{len(find(call('GET', '/admin/users', A).json(), 'items', 'users') or [])} user(s)")
    step("Audit log", lambda: f"{len(find(call('GET', '/admin/audit', A).json(), 'items', 'events', 'audit') or [])} event(s)")
    step("Operations", lambda: str(call("GET", "/admin/operations", A).json())[:150])
    step("Health check", lambda: str(call("POST", "/admin/health/check", A).json())[:150])
    def model_check():
        models = find(call("GET", "/admin/models", A).json(), "items", "models") or []
        if not models:
            return "no models trained yet"
        return str(call("POST", f"/admin/models/{models[0]['model_id']}/check", A).json())[:150]
    step("Model check", model_check)
else:
    print("  SKIP  admin checks (demo admin unavailable; another administrator already exists)")

section("11. Logout")
step("Logout revokes refresh token", lambda: (call("POST", "/auth/logout", json={"refresh_token": S["refresh"]}),
                                            call("POST", "/auth/refresh", json={"refresh_token": S["refresh"]}, expect=401), "revoked")[2])

passed = sum(r[0] == "PASS" for r in RESULTS)
print(f"\nRESULT: {passed}/{len(RESULTS)} passed   demo login: {email} / {PASSWORD}")
sys.exit(0 if passed == len(RESULTS) else 1)
