from psycopg.types.json import Jsonb

from app.portfolio.risk import PortfolioError
from app.trading.lifecycle import BotEvent, InvalidBotTransition, transition


class TradingService:
    def __init__(self, repository):
        self.repository = repository

    def update(self, user_id, bot_id, config):
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if row['state'] != 'stopped':
                raise PortfolioError('Stop and reset the bot before changing configuration', 409)
            if config.portfolio_id != row['portfolio_id'] or config.symbol != row['symbol']:
                raise PortfolioError('Portfolio and symbol cannot be changed', 409)
            return c.execute('''UPDATE trading_bots SET config=%s,revision=revision+1,updated_at=now()
                WHERE bot_id=%s RETURNING *''', (Jsonb(config.model_dump(mode='json')), bot_id)).fetchone()

    def control(self, user_id, bot_id, action):
        events = {'start': BotEvent.START, 'stop': BotEvent.REQUEST_STOP, 'reset': BotEvent.RESET}
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if action == 'start':
                heartbeat = c.execute("SELECT 1 FROM trading_worker_heartbeat WHERE seen_at > now()-interval '90 seconds' LIMIT 1").fetchone()
                if not heartbeat:
                    raise PortfolioError('Trading worker is not ready', 503)
            try:
                snapshot = transition(self.repository.snapshot(row), events[action])
            except InvalidBotTransition as exc:
                raise PortfolioError(str(exc), 409) from None
            # Paper fills are committed synchronously under this same lock;
            # no outstanding external submission remains after acquiring it.
            if snapshot.state.value == 'stopping':
                snapshot = transition(snapshot, BotEvent.STOP_COMPLETED)
            if row['state'] == snapshot.state.value:
                return row
            return c.execute('''UPDATE trading_bots SET state=%s,revision=revision+1,
                failures=0,last_error=NULL,next_run_at=now(),updated_at=now() WHERE bot_id=%s RETURNING *''',
                (snapshot.state.value, bot_id)).fetchone()
