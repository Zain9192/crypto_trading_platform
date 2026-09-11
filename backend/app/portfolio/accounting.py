"""Decimal, average-cost accounting. All persisted amounts use eight decimal places."""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

ZERO = Decimal("0")
UNIT = Decimal("0.00000001")


def money(value):
    with localcontext() as context:
        context.prec = 50
        return Decimal(value).quantize(UNIT, rounding=ROUND_HALF_EVEN)


def notional(quantity, price):
    with localcontext() as context:
        context.prec = 50
        return money(quantity * price)


def apply_fill(holding, side, quantity, price, fee):
    """Buy fees join basis; sell fees reduce proceeds; final sale consumes all basis."""
    with localcontext() as context:
        context.prec = 50
        gross = notional(quantity, price)
        if side == "buy":
            return {"quantity": holding["quantity"] + quantity,
                    "cost_basis": holding["cost_basis"] + gross + fee,
                    "realized_pnl": holding["realized_pnl"]}, -(gross + fee), ZERO
        if quantity > holding["quantity"]:
            raise ValueError("Insufficient holding")
        basis = holding["cost_basis"] if quantity == holding["quantity"] else money(
            holding["cost_basis"] * quantity / holding["quantity"])
        realized = gross - fee - basis
        return {"quantity": holding["quantity"] - quantity,
                "cost_basis": holding["cost_basis"] - basis,
                "realized_pnl": holding["realized_pnl"] + realized}, gross - fee, realized


def reservations(orders):
    cash, quantities = ZERO, {}
    for order in orders:
        if order["side"] == "buy":
            cash += order["notional"] + order["fee"]
        else:
            symbol = order["symbol"]
            quantities[symbol] = quantities.get(symbol, ZERO) + order["quantity"]
    return cash, quantities


def position_symbols(holdings, orders):
    return {h["symbol"] for h in holdings if h["quantity"] > 0} | {
        o["symbol"] for o in orders if o["side"] == "buy"}
