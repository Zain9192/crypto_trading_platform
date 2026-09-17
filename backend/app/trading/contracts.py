from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.exchange.contracts import Contract, Symbol
from app.portfolio.schemas import Positive
from app.market.schemas import MarketInterval


class BotState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class BotConfig(Contract):
    portfolio_id: int | None = Field(default=None, gt=0)
    connection_id: UUID | None = None
    symbol: Symbol
    interval: MarketInterval = "1d"
    mode: Literal["paper", "sandbox"] = "paper"
    enabled: bool = Field(default=False, strict=True)
    confidence_threshold: Decimal = Field(default=Decimal("0.7"), ge=Decimal("0.5"), le=1, allow_inf_nan=False)
    order_amount: Positive
    max_open_trades: int = Field(default=1, ge=1, le=100)
    stop_loss_pct: Decimal | None = Field(default=None, gt=0, lt=100, decimal_places=4, allow_inf_nan=False)
    take_profit_pct: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=4, allow_inf_nan=False)

    min_quote_per_order: Positive = Decimal("1")
    max_quote_per_order: Positive = Decimal("1000")
    max_open_positions: int = Field(default=5, ge=1, le=100)
    slippage_bps: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def environment(self):
        base, quote = self.symbol.split("/")
        if len(base) > 20:
            raise ValueError("Asset symbol is too long")
        if self.mode == "paper":
            if self.portfolio_id is None or self.connection_id is not None or quote != "USD":
                raise ValueError("Paper bots require a portfolio and BASE/USD pair")
        elif self.connection_id is None or self.portfolio_id is not None or quote != "USDT":
            raise ValueError("Sandbox bots require a Binance Testnet connection and BASE/USDT pair")
        if self.min_quote_per_order > self.max_quote_per_order:
            raise ValueError("Minimum order value must not exceed maximum")
        return self


class BotSnapshot(Contract):
    bot_id: UUID
    config: BotConfig
    state: BotState = BotState.STOPPED
