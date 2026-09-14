from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Symbol = Annotated[str, Field(pattern=r"^[A-Z0-9]+/[A-Z0-9]+$", max_length=41)]


class ExchangeName(str, Enum):
    BINANCE = "binance"
    COINBASE = "coinbase"
    KRAKEN = "kraken"


class ExchangeError(RuntimeError):
    """Safe application error; provider payloads must not enter user-visible messages."""


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Credentials(Contract):
    api_key: SecretStr
    api_secret: SecretStr
    passphrase: SecretStr | None = None

    @field_validator("api_key", "api_secret", "passphrase")
    @classmethod
    def nonempty_secret(cls, value):
        if value is not None and (not value.get_secret_value().strip() or len(value.get_secret_value()) > 16384):
            raise ValueError("Credential must contain between 1 and 16384 characters")
        return value


class ConnectionPolicy(Contract):
    sandbox: bool = True
    read_only: bool = True

    def require_mutation(self, *, sandbox_supported: bool):
        # Capabilities must come from the adapter, never from an HTTP request.
        if self.read_only:
            raise ExchangeError("Connection is read-only")
        if not self.sandbox:
            raise ExchangeError("Live exchange mutations are disabled")
        if not sandbox_supported:
            raise ExchangeError("This adapter does not support sandbox mutations")


class OrderRequest(Contract):
    client_order_id: UUID
    symbol: Symbol
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    amount: Positive
    price: Positive | None = None

    @model_validator(mode="after")
    def price_matches_type(self):
        if self.order_type == "limit" and self.price is None:
            raise ValueError("Limit orders require a price")
        if self.order_type == "market" and self.price is not None:
            raise ValueError("Market orders must not include a limit price")
        return self


class Balance(Contract):
    currency: str
    free: Nonnegative
    used: Nonnegative
    total: Nonnegative


class PriceQuote(Contract):
    symbol: Symbol
    price: Positive
    observed_at: datetime


class Order(Contract):
    order_id: str
    symbol: Symbol
    side: Literal["buy", "sell"]
    status: Literal["open", "closed", "canceled", "expired", "rejected", "unknown"]
    amount: Positive
    filled: Nonnegative
    price: Positive | None = None


class Trade(Contract):
    trade_id: str
    order_id: str | None = None
    symbol: Symbol
    side: Literal["buy", "sell"]
    amount: Positive
    price: Positive
    executed_at: datetime


class ExchangeAdapter(Protocol):
    """Spot-only normalized boundary; adapters must enforce ConnectionPolicy.

    Decimal values remain strings until the transport library's precision helpers
    normalize them. Order placement is never automatically retried after timeouts:
    reconcile the client order ID first. No withdrawal or leverage operations.
    """

    exchange: ExchangeName

    def connect(self) -> None: ...
    def get_balance(self) -> list[Balance]: ...
    def get_price(self, symbol: str) -> PriceQuote: ...
    def place_order(self, request: OrderRequest) -> Order: ...
    def cancel_order(self, order_id: str, symbol: str) -> Order: ...
    def get_order(self, order_id: str, symbol: str) -> Order: ...
    def get_trades(self, symbol: str, since: datetime | None = None, limit: int = 100) -> list[Trade]: ...
