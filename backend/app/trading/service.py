from psycopg.types.json import Jsonb

from app.portfolio.risk import PortfolioError
from app.trading.lifecycle import BotEvent, InvalidBotTransition, transition


class TradingService:
    def __init__(self, repository):
        self.repository = repository

    def update(self, user_id, bot_id, config):
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if row['state'] != 'stopped' or row['close_requested']:
                raise PortfolioError('Stop and reset the bot before changing configuration', 409)
            if (config.portfolio_id != row['portfolio_id'] or config.symbol != row['symbol'] or
                    config.connection_id != row['connection_id'] or config.mode != row['config']['mode']):
                raise PortfolioError('Portfolio and symbol cannot be changed', 409)
            if row['connection_id'] and self.repository.unresolved(c, bot_id):
                raise PortfolioError('Reconcile outstanding sandbox orders before editing settings', 409)
            return c.execute('''UPDATE trading_bots SET config=%s,revision=revision+1,updated_at=now()
                WHERE bot_id=%s RETURNING *''', (Jsonb(config.model_dump(mode='json')), bot_id)).fetchone()

    def control(self, user_id, bot_id, action):
        events = {'start': BotEvent.START, 'stop': BotEvent.REQUEST_STOP, 'reset': BotEvent.RESET}
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if action in ('start', 'reset') and row['connection_id'] and self.repository.unresolved(c, bot_id):
                raise PortfolioError('Reconcile outstanding sandbox orders before restarting', 409)
            if action == 'start':
                if row['close_requested']:
                    raise PortfolioError('Wait for the requested position close before restarting', 409)
                heartbeat = c.execute("SELECT 1 FROM trading_worker_heartbeat WHERE seen_at > now()-interval '90 seconds' LIMIT 1").fetchone()
                if not heartbeat:
                    raise PortfolioError('Trading worker is not ready', 503)
            try:
                snapshot = transition(self.repository.snapshot(row), events[action])
            except InvalidBotTransition as exc:
                raise PortfolioError(str(exc), 409) from None
            # Paper fills are committed synchronously under this same lock;
            # no outstanding external submission remains after acquiring it.
            pending = self.repository.unresolved(c, bot_id) if row['connection_id'] else []
            if action == 'stop' and pending:
                c.execute("UPDATE sandbox_orders SET cancel_requested=true,next_reconcile_at=now() WHERE bot_id=%s AND status IN ('submitting','unknown','open','partially_filled')", (bot_id,))
            if snapshot.state.value == 'stopping' and not pending:
                snapshot = transition(snapshot, BotEvent.STOP_COMPLETED)
            if row['state'] == snapshot.state.value:
                return row
            return c.execute('''UPDATE trading_bots SET state=%s,revision=revision+1,
                failures=0,last_error=NULL,next_run_at=now(),updated_at=now() WHERE bot_id=%s RETURNING *''',
                (snapshot.state.value, bot_id)).fetchone()

    def sandbox_action(self, user_id, bot_id, action, order_id=None):
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if row['connection_id'] is None:
                raise PortfolioError('This action requires a sandbox bot', 422)
            if action == 'close':
                if row['state'] not in ('stopped', 'error'):
                    raise PortfolioError('Stop the bot before closing its sandbox position', 409)
                if self.repository.unresolved(c, bot_id):
                    raise PortfolioError('Reconcile outstanding orders before closing', 409)
                c.execute('UPDATE trading_bots SET close_requested=true,next_run_at=now(),revision=revision+1 WHERE bot_id=%s', (bot_id,))
            else:
                order = c.execute('SELECT * FROM sandbox_orders WHERE order_id=%s AND bot_id=%s', (order_id, bot_id)).fetchone()
                if order is None:
                    raise PortfolioError('Order not found', 404)
                c.execute("""UPDATE sandbox_orders SET cancel_requested=cancel_requested OR %s,next_reconcile_at=now()
                    WHERE order_id=%s AND status IN ('submitting','unknown','open','partially_filled')""", (action == 'cancel', order_id))
                c.execute('UPDATE trading_bots SET next_run_at=now() WHERE bot_id=%s', (bot_id,))
            return {'message': 'Request queued for the sandbox worker'}
