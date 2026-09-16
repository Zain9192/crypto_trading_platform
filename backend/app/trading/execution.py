from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from app.trading.contracts import BotConfig


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class RiskDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class TradingSignal(BaseModel):
    symbol: str
    signal: Signal
    confidence: Decimal = Field(ge=0, le=1)
    expected_return: Decimal = Decimal("0")


class ExecutionDecision(BaseModel):
    approved: bool
    risk: RiskDecision
    reason: str


class RiskValidator:
    def validate(
        self,
        config: BotConfig,
        confidence: Decimal,
        available_balance: Decimal,
        open_trades: int,
    ) -> ExecutionDecision:
        if confidence < config.confidence_threshold:
            return ExecutionDecision(
                approved=False,
                risk=RiskDecision.REJECTED,
                reason="Prediction confidence below configured threshold",
            )

        if available_balance < config.order_amount:
            return ExecutionDecision(
                approved=False,
                risk=RiskDecision.REJECTED,
                reason="Insufficient available balance",
            )

        if open_trades >= config.max_open_trades:
            return ExecutionDecision(
                approved=False,
                risk=RiskDecision.REJECTED,
                reason="Maximum open trades reached",
            )

        return ExecutionDecision(
            approved=True,
            risk=RiskDecision.APPROVED,
            reason="Risk checks passed",
        )


class TradingEngine:
    def __init__(self, risk_validator: RiskValidator | None = None):
        self.risk_validator = risk_validator or RiskValidator()

    def create_execution_plan(
        self,
        bot_id: UUID,
        config: BotConfig,
        signal: TradingSignal,
        available_balance: Decimal,
        open_trades: int,
    ) -> dict:
        decision = self.risk_validator.validate(
            config,
            signal.confidence,
            available_balance,
            open_trades,
        )

        return {
            "bot_id": bot_id,
            "symbol": signal.symbol,
            "signal": signal.signal,
            "execute": decision.approved,
            "risk": decision.risk,
            "reason": decision.reason,
        }
