from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.exchange.contracts import Contract, Symbol
from app.portfolio.schemas import Positive
from app.market.schemas import MarketInterval


class BotState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class BotConfig(Contract):
    portfolio_id: int = Field(gt=0)
    symbol: Symbol
    interval: MarketInterval = "1d"
    mode: Literal["paper"] = "paper"
    enabled: bool = Field(default=False, strict=True)
    confidence_threshold: Decimal = Field(default=Decimal("0.7"), ge=Decimal("0.5"), le=1, allow_inf_nan=False)
    order_amount: Positive
    max_open_trades: int = Field(default=1, ge=1, le=100)
    stop_loss_pct: Decimal | None = Field(default=None, gt=0, lt=100, allow_inf_nan=False)
    take_profit_pct: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)

    @field_validator("symbol")
    @classmethod
    def paper_currency(cls, value):
        base, quote = value.split("/")
        if quote != "USD" or len(base) > 20:
            raise ValueError("Paper bots require a BASE/USD pair")
        return value


class BotSnapshot(Contract):
    bot_id: UUID
    config: BotConfig
    state: BotState = BotState.STOPPED
