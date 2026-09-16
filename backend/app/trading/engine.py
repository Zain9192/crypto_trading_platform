from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class TradeSignal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class RiskDecision:
    allowed: bool
    reason: Optional[str] = None


@dataclass
class ExecutionDecision:
    signal: TradeSignal
    symbol: str
    quantity: Decimal


class TradingEngine:
    """Core automated trading orchestration layer.

    Exchange execution, portfolio updates and persistence are injected later.
    This keeps decision flow isolated from external systems.
    """

    def __init__(self, risk_checker=None, executor=None):
        self.risk_checker = risk_checker
        self.executor = executor

    def validate_trade(self, decision: ExecutionDecision) -> RiskDecision:
        if self.risk_checker is None:
            return RiskDecision(True)

        return self.risk_checker.check(decision)

    def execute(self, decision: ExecutionDecision):
        risk = self.validate_trade(decision)
        if not risk.allowed:
            return {"status": "rejected", "reason": risk.reason}

        if self.executor is None:
            return {"status": "ready", "decision": decision}

        return self.executor.execute(decision)
