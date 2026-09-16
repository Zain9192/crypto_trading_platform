from dataclasses import dataclass
from decimal import Decimal

from app.trading.contracts import BotSnapshot


@dataclass(frozen=True)
class ExecutionResult:
    approved: bool
    reason: str
    action: str | None = None


class TradingExecutor:
    """Coordinates validated trading decisions before exchange execution."""

    def evaluate_signal(
        self,
        bot: BotSnapshot,
        confidence: Decimal,
        balance_available: Decimal,
        open_trades: int,
    ) -> ExecutionResult:
        if not bot.config.enabled:
            return ExecutionResult(False, "bot_disabled")

        if confidence < bot.config.confidence_threshold:
            return ExecutionResult(False, "confidence_below_threshold")

        if balance_available < bot.config.order_amount:
            return ExecutionResult(False, "insufficient_balance")

        if open_trades >= bot.config.max_open_trades:
            return ExecutionResult(False, "maximum_open_trades_reached")

        return ExecutionResult(True, "approved", "execute_spot_order")
