from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import Field

from app.exchange.contracts import Contract, Symbol
from app.portfolio.risk import PortfolioError


class Signal(str, Enum):
    BUY = 'buy'
    SELL = 'sell'
    HOLD = 'hold'


class TradingSignal(Contract):
    symbol: Symbol
    signal: Signal
    confidence: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    event_key: str = Field(min_length=1, max_length=200)
    expires_at: datetime


def prediction_signal(config, forecast, now):
    if forecast.symbol != config.symbol.split('/')[0] or forecast.interval != config.interval:
        raise PortfolioError('Prediction does not match bot configuration')
    if (forecast.as_of.tzinfo is None or forecast.forecast_for.tzinfo is None or
            forecast.as_of > now or forecast.forecast_for <= now):
        raise PortfolioError('Prediction is stale or has invalid timestamps')
    action = Signal.HOLD
    if forecast.direction == 'up' and forecast.expected_return > 0:
        action = Signal.BUY
    elif forecast.direction == 'down' and forecast.expected_return < 0:
        action = Signal.SELL
    # Model switches and restarts must not trade the same candle twice.
    return TradingSignal(symbol=config.symbol, signal=action,
                         confidence=Decimal(str(forecast.confidence)),
                         event_key=f'prediction:{config.interval}:{forecast.as_of.isoformat()}',
                         expires_at=forecast.forecast_for)
