from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.exchange.contracts import Contract, Positive, Symbol
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
    enabled: Literal[False] = False
    confidence_threshold: Decimal = Field(default=Decimal("0.7"), ge=Decimal("0.5"), le=1, allow_inf_nan=False)
    order_amount: Positive
    max_open_trades: int = Field(default=1, ge=1, le=100)
    stop_loss_pct: Decimal | None = Field(default=None, gt=0, lt=100, allow_inf_nan=False)
    take_profit_pct: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)


class BotSnapshot(Contract):
    bot_id: UUID
    config: BotConfig
    state: Literal[BotState.STOPPED] = BotState.STOPPED
