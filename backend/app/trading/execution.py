from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.trading.contracts import BotConfig


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class RiskDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class OrderStatus(str, Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    FILLED = "filled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TradingSignal(BaseModel):
    symbol: str
    signal: Signal
    confidence: Decimal = Field(ge=0, le=1)
    expected_return: Decimal = Decimal("0")


class ExecutionDecision(BaseModel):
    approved: bool
    risk: RiskDecision
    reason: str


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: Signal
    amount: Decimal


@dataclass(frozen=True)
class ExecutionOrder:
    order_id: UUID
    intent: OrderIntent
    status: OrderStatus


class RiskValidator:
    def validate(
        self,
        config: BotConfig,
        confidence: Decimal,
        available_balance: Decimal,
        open_trades: int,
    ) -> ExecutionDecision:
        if confidence < config.confidence_threshold:
            return ExecutionDecision(False, RiskDecision.REJECTED, "Prediction confidence below configured threshold")
        if available_balance < config.order_amount:
            return ExecutionDecision(False, RiskDecision.REJECTED, "Insufficient available balance")
        if open_trades >= config.max_open_trades:
            return ExecutionDecision(False, RiskDecision.REJECTED, "Maximum open trades reached")
        return ExecutionDecision(True, RiskDecision.APPROVED, "Risk checks passed")


class ExchangeExecutionAdapter:
    def submit(self, intent: OrderIntent) -> ExecutionOrder:
        return ExecutionOrder(
            order_id=uuid4(),
            intent=intent,
            status=OrderStatus.SUBMITTED,
        )


class TradingEngine:
    def __init__(self, risk_validator: RiskValidator | None = None, executor: ExchangeExecutionAdapter | None = None):
        self.risk_validator = risk_validator or RiskValidator()
        self.executor = executor or ExchangeExecutionAdapter()

    def create_execution_plan(
        self,
        bot_id: UUID,
        config: BotConfig,
        signal: TradingSignal,
        available_balance: Decimal,
        open_trades: int,
    ) -> dict:
        decision = self.risk_validator.validate(config, signal.confidence, available_balance, open_trades)
        intent = None
        order = None

        if decision.approved and signal.signal != Signal.HOLD:
            intent = OrderIntent(signal.symbol, signal.signal, config.order_amount)
            order = self.executor.submit(intent)

        return {
            "bot_id": bot_id,
            "symbol": signal.symbol,
            "signal": signal.signal,
            "execute": decision.approved,
            "risk": decision.risk,
            "reason": decision.reason,
            "order_intent": intent,
            "execution_order": order,
        }
