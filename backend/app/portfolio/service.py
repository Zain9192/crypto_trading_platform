from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.market.providers import ProviderError
from app.portfolio.accounting import ZERO, apply_fill, money, notional, position_symbols, reservations
from app.portfolio.risk import PortfolioError, validate_order
from app.portfolio.schemas import RiskSettings


class PortfolioService:
    def __init__(self, repository, market):
        self.repository = repository
        self.market = market

    def create(self, user_id, request):
        with self.repository.transaction() as c:
            return c.execute("""INSERT INTO portfolios (user_id, mode, initial_cash, cash_balance)
                VALUES (%s,'paper',%s,%s) ON CONFLICT (user_id) WHERE mode='paper'
                DO UPDATE SET user_id=EXCLUDED.user_id RETURNING portfolio_id, mode, initial_cash, created_at""",
                (user_id, request.initial_cash, request.initial_cash)).fetchone()

    def list(self, user_id):
        with self.repository.transaction() as c:
            return c.execute("""SELECT portfolio_id, mode, initial_cash, created_at FROM portfolios
                WHERE user_id=%s AND mode='paper' ORDER BY portfolio_id""", (user_id,)).fetchall()

    def overview(self, user_id, portfolio_id):
        with self.repository.transaction() as c:
            portfolio = self.repository.owned(c, user_id, portfolio_id)
            holdings, pending = self.repository.state(c, portfolio_id)
        # Network calls occur after releasing the accounting lock. Snapshot balances remain consistent.
        try:
            assets, _ = self.market.get_top_assets(limit=50)
        except ProviderError:
            assets = []
        quotes = {}
        now = datetime.now(timezone.utc)
        for asset in assets:
            if asset.current_price is None or asset.last_updated is None:
                continue
            price = Decimal(str(asset.current_price))
            timestamp = asset.last_updated
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                continue
            if price.is_finite() and price > 0 and -30 <= (now - timestamp).total_seconds() <= 300:
                quotes[asset.symbol.upper()] = (price, timestamp)
        return value_snapshot(portfolio, holdings, pending, quotes, now)

    def settings(self, user_id, portfolio_id, settings):
        with self.repository.transaction() as c:
            self.repository.owned(c, user_id, portfolio_id)
            holdings, pending = self.repository.state(c, portfolio_id)
            if len(pending) > settings.max_open_trades or len(position_symbols(holdings, pending)) > settings.max_open_positions:
                raise PortfolioError("Close or cancel positions/trades before lowering these limits")
            c.execute("UPDATE portfolios SET risk_settings=%s WHERE portfolio_id=%s",
                      (Jsonb(settings.model_dump(mode="json")), portfolio_id))
        return settings.model_dump()

    def preview(self, user_id, portfolio_id, request):
        with self.repository.transaction() as c:
            p = self.repository.owned(c, user_id, portfolio_id)
            holdings, pending = self.repository.state(c, portfolio_id)
            return {"valid": True, **validate_order(p, holdings, pending, request, RiskSettings.model_validate(p["risk_settings"]))}

    def reserve(self, user_id, portfolio_id, request):
        with self.repository.transaction() as c:
            return self.reserve_in_transaction(c, user_id, portfolio_id, request)

    def reserve_in_transaction(self, c, user_id, portfolio_id, request, managed=False):
        p = self.repository.owned(c, user_id, portfolio_id)
        existing = c.execute("SELECT * FROM portfolio_orders WHERE portfolio_id=%s AND client_order_id=%s",
                             (portfolio_id, request.client_order_id)).fetchone()
        if existing:
            if any(existing[key] != getattr(request, key) for key in (
                    "symbol", "side", "quantity", "simulation_price", "fee")):
                raise PortfolioError("Client order ID was already used with different details", 409)
            return existing
        holdings, pending = self.repository.state(c, portfolio_id)
        if request.side == 'sell' and not managed and c.execute("SELECT to_regclass('trading_positions')").fetchone()['to_regclass']:
            protected = c.execute("""SELECT COALESCE(sum(tp.quantity),0) AS quantity FROM trading_positions tp
                JOIN trading_bots b USING(bot_id) WHERE b.portfolio_id=%s AND b.symbol=%s""",
                (portfolio_id, request.symbol + '/USD')).fetchone()['quantity']
            held = next((h['quantity'] for h in holdings if h['symbol'] == request.symbol), ZERO)
            _, reserved = reservations(pending)
            if request.quantity > held - protected - reserved.get(request.symbol, ZERO):
                raise PortfolioError('Bot-managed units must be closed through the bot', 409)
        result = validate_order(p, holdings, pending, request, RiskSettings.model_validate(p["risk_settings"]))
        return c.execute("""INSERT INTO portfolio_orders
            (order_id,portfolio_id,client_order_id,symbol,side,quantity,simulation_price,fee,notional,stop_loss_price,take_profit_price)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (uuid4(), portfolio_id, request.client_order_id, request.symbol, request.side,
             request.quantity, request.simulation_price, request.fee, result["notional"],
             result["stop_loss_price"], result["take_profit_price"])).fetchone()

    def complete(self, user_id, portfolio_id, order_id, action):
        with self.repository.transaction() as c:
            return self.complete_in_transaction(c, user_id, portfolio_id, order_id, action)

    def complete_in_transaction(self, c, user_id, portfolio_id, order_id, action):
        self.repository.owned(c, user_id, portfolio_id)
        order = c.execute("SELECT * FROM portfolio_orders WHERE portfolio_id=%s AND order_id=%s",
                          (portfolio_id, order_id)).fetchone()
        if order is None:
            raise PortfolioError("Order not found", 404)
        target = "filled" if action == "fill" else "cancelled"
        if order["status"] == target:
            return order
        if order["status"] != "pending":
            raise PortfolioError("Order is already " + order["status"], 409)
        if action == "fill":
            c.execute("""INSERT INTO portfolio_holdings (portfolio_id,symbol) VALUES (%s,%s)
                ON CONFLICT DO NOTHING""", (portfolio_id, order["symbol"]))
            holding = c.execute("SELECT * FROM portfolio_holdings WHERE portfolio_id=%s AND symbol=%s",
                                (portfolio_id, order["symbol"])).fetchone()
            updated, cash_change, realized = apply_fill(holding, order["side"], order["quantity"], order["simulation_price"], order["fee"])
            c.execute("""UPDATE portfolio_holdings SET quantity=%s,cost_basis=%s,realized_pnl=%s
                WHERE portfolio_id=%s AND symbol=%s""",
                (updated["quantity"], updated["cost_basis"], updated["realized_pnl"], portfolio_id, order["symbol"]))
            c.execute("UPDATE portfolios SET cash_balance=cash_balance+%s WHERE portfolio_id=%s", (cash_change, portfolio_id))
            c.execute("""INSERT INTO portfolio_trades (portfolio_id,order_id,symbol,side,quantity,price,fee,realized_pnl)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (portfolio_id, order_id, order["symbol"], order["side"],
                order["quantity"], order["simulation_price"], order["fee"], realized))
        return c.execute("UPDATE portfolio_orders SET status=%s,completed_at=now() WHERE order_id=%s RETURNING *",
                         (target, order_id)).fetchone()

    def history(self, user_id, portfolio_id, limit, before):
        with self.repository.transaction() as c:
            self.repository.owned(c, user_id, portfolio_id)
            rows = c.execute("""SELECT * FROM portfolio_trades WHERE portfolio_id=%s
                AND (%s::bigint IS NULL OR trade_id < %s) ORDER BY trade_id DESC LIMIT %s""",
                (portfolio_id, before, before, limit + 1)).fetchall()
        return {"items": rows[:limit], "next_cursor": rows[limit - 1]["trade_id"] if len(rows) > limit else None}


def value_snapshot(portfolio, holdings, pending, quotes, now):
    reserved, reserved_units = reservations(pending)
    positions, missing = [], []
    realized = sum((h["realized_pnl"] for h in holdings), ZERO)
    for holding in holdings:
        if not holding["quantity"]:
            continue
        quote = quotes.get(holding["symbol"])
        value = notional(holding["quantity"], quote[0]) if quote else None
        if quote is None:
            missing.append(holding["symbol"])
        positions.append({**holding, "available_quantity": holding["quantity"] - reserved_units.get(holding["symbol"], ZERO),
                          "average_cost": money(holding["cost_basis"] / holding["quantity"]),
                          "current_price": quote[0] if quote else None,
                          "price_as_of": quote[1] if quote else None, "market_value": value,
                          "unrealized_pnl": value - holding["cost_basis"] if value is not None else None})
    total = None if missing else portfolio["cash_balance"] + sum((p["market_value"] for p in positions), ZERO)
    for p in positions:
        p["allocation_pct"] = money(p["market_value"] / total * 100) if total and p["market_value"] is not None else None
    unrealized = None if missing else sum((p["unrealized_pnl"] for p in positions), ZERO)
    return {"portfolio_id": portfolio["portfolio_id"], "mode": "paper", "currency": "USD",
            "initial_cash": portfolio["initial_cash"], "cash_balance": portfolio["cash_balance"],
            "reserved_cash": reserved, "available_cash": portfolio["cash_balance"] - reserved,
            "total_value": total, "realized_pnl": realized, "unrealized_pnl": unrealized,
            "total_pnl": None if missing else realized + unrealized,
            "cash_allocation_pct": money(portfolio["cash_balance"] / total * 100) if total else None,
            "valuation_complete": not missing, "unpriced_symbols": missing, "valued_at": now,
            "holdings": positions, "pending_orders": pending, "risk_settings": portfolio["risk_settings"]}
