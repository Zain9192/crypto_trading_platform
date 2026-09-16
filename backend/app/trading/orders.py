from uuid import UUID, uuid5


def client_order_id(bot_id: UUID, event_key: str) -> UUID:
    return uuid5(bot_id, event_key)
