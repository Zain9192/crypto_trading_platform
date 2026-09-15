from enum import Enum

from app.trading.contracts import BotSnapshot, BotState


class BotEvent(str, Enum):
    START = "start"
    REQUEST_STOP = "request_stop"
    STOP_COMPLETED = "stop_completed"
    FAIL = "fail"
    RESET = "reset"


class InvalidBotTransition(ValueError):
    pass


_TRANSITIONS = {
    (BotState.STOPPED, BotEvent.START): BotState.RUNNING,
    (BotState.RUNNING, BotEvent.START): BotState.RUNNING,
    (BotState.RUNNING, BotEvent.REQUEST_STOP): BotState.STOPPING,
    (BotState.STOPPING, BotEvent.REQUEST_STOP): BotState.STOPPING,
    (BotState.STOPPED, BotEvent.REQUEST_STOP): BotState.STOPPED,
    (BotState.STOPPING, BotEvent.STOP_COMPLETED): BotState.STOPPED,
    (BotState.STOPPED, BotEvent.STOP_COMPLETED): BotState.STOPPED,
    (BotState.RUNNING, BotEvent.FAIL): BotState.ERROR,
    (BotState.STOPPING, BotEvent.FAIL): BotState.ERROR,
    (BotState.ERROR, BotEvent.FAIL): BotState.ERROR,
    (BotState.ERROR, BotEvent.RESET): BotState.STOPPED,
    (BotState.STOPPED, BotEvent.RESET): BotState.STOPPED,
}


def transition(bot: BotSnapshot, event: BotEvent) -> BotSnapshot:
    # Pure state calculation. A future service must persist under a lock and
    # verify ownership, risk settings and worker readiness before starting.
    event = BotEvent(event)
    if event == BotEvent.START and not bot.config.enabled:
        raise InvalidBotTransition("Enable the bot configuration before starting")
    target = _TRANSITIONS.get((bot.state, event))
    if target is None:
        raise InvalidBotTransition(f"Cannot {event.value} a bot in {bot.state.value} state")
    return BotSnapshot(bot_id=bot.bot_id, config=bot.config, state=target)
