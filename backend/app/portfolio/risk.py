from app.portfolio.accounting import ZERO, money, notional, position_symbols, reservations


class PortfolioError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def validate_order(portfolio, holdings, pending, request, settings):
    gross = notional(request.quantity, request.simulation_price)
    if gross <= 0 or gross > 1_000_000_000_000:
        raise PortfolioError("Order notional must be between 0.00000001 and 1000000000000 USD")
    if request.fee >= gross:
        raise PortfolioError("Fee must be smaller than order notional")
    cash_reserved, units_reserved = reservations(pending)
    if len(pending) >= settings.max_open_trades:
        raise PortfolioError("Maximum open trades reached")
    if request.side == "buy":
        investment = gross + request.fee
        if not settings.min_investment <= investment <= settings.max_investment:
            raise PortfolioError("Investment including fee is outside configured limits")
        if investment > portfolio["cash_balance"] - cash_reserved:
            raise PortfolioError("Insufficient available cash")
        positions = position_symbols(holdings, pending) | {request.symbol}
        if len(positions) > settings.max_open_positions:
            raise PortfolioError("Maximum open positions reached")
    else:
        holding = next((h for h in holdings if h["symbol"] == request.symbol), None)
        available = (holding["quantity"] if holding else ZERO) - units_reserved.get(request.symbol, ZERO)
        if request.quantity > available:
            raise PortfolioError("Insufficient available holding")
    # Long-spot thresholds are saved on buys. They are settings, not executable orders.
    stop = take = None
    if request.side == "buy":
        if settings.stop_loss_pct is not None:
            stop = money(request.simulation_price * (1 - settings.stop_loss_pct / 100))
            if stop <= 0 or stop >= request.simulation_price:
                raise PortfolioError("Stop-loss rounds outside the valid price range")
        if settings.take_profit_pct is not None:
            take = money(request.simulation_price * (1 + settings.take_profit_pct / 100))
            if take <= request.simulation_price:
                raise PortfolioError("Take-profit rounds outside the valid price range")
    return {"notional": gross, "cash_required": gross + request.fee if request.side == "buy" else ZERO,
            "stop_loss_price": stop, "take_profit_price": take}
