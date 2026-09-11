from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

Money = Annotated[Decimal, Field(ge=0, le=1_000_000_000, max_digits=18, decimal_places=8)]
Positive = Annotated[Decimal, Field(gt=0, le=1_000_000_000, max_digits=18, decimal_places=8)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortfolioCreate(StrictModel):
    initial_cash: Positive = Decimal("10000")


class RiskSettings(StrictModel):
    min_investment: Positive = Decimal("1")
    max_investment: Positive = Decimal("10000")
    max_open_positions: int = Field(default=10, ge=1, le=100)
    max_open_trades: int = Field(default=10, ge=1, le=100)
    stop_loss_pct: Decimal | None = Field(default=Decimal("5"), gt=0, lt=100, decimal_places=4)
    take_profit_pct: Decimal | None = Field(default=Decimal("10"), gt=0, le=1000, decimal_places=4)

    @model_validator(mode="after")
    def check_bounds(self):
        if self.min_investment > self.max_investment:
            raise ValueError("Minimum investment must not exceed maximum investment")
        return self


class PaperOrderCreate(StrictModel):
    client_order_id: UUID
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    side: Literal["buy", "sell"]
    quantity: Positive
    simulation_price: Positive
    fee: Money = Decimal("0")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value):
        return value.upper()
