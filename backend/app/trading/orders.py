from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime, timezone


class OrderStatus(str, Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OrderType(str, Enum):
    MARKET = "market"


class OrderRecord:
    def __init__(
        self,
        bot_id: UUID,
        symbol: str,
        side: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        idempotency_key: str | None = None,
    ):
        self.id = uuid4()
        self.bot_id = bot_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.order_type = order_type
        self.status = OrderStatus.CREATED
        self.idempotency_key = idempotency_key or str(self.id)
        self.created_at = datetime.now(timezone.utc)


class OrderLifecycleManager:
    _allowed = {
        OrderStatus.CREATED: {OrderStatus.SUBMITTED, OrderStatus.FAILED},
        OrderStatus.SUBMITTED: {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        },
        OrderStatus.PARTIALLY_FILLED: {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        },
        OrderStatus.FILLED: set(),
        OrderStatus.CANCELLED: set(),
        OrderStatus.FAILED: set(),
    }

    def transition(self, order: OrderRecord, target: OrderStatus) -> OrderRecord:
        if target not in self._allowed[order.status]:
            raise ValueError(
                f"Invalid order transition {order.status.value} -> {target.value}"
            )
        order.status = target
        return order
