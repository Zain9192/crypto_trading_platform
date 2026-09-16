from datetime import datetime, timezone
from decimal import Decimal

from app.portfolio.accounting import money
from app.portfolio.risk import PortfolioError
from app.trading.executor import TradingExecutor


class TradingEngine:
    def __init__(self, repository):
        self.repository = repository
        self.executor = TradingExecutor(repository)

    @staticmethod
    def quote(asset, now):
        if asset is None or asset.last_updated is None or asset.last_updated.tzinfo is None:
            raise PortfolioError('A timestamped USD market quote is required')
        price = Decimal(str(asset.current_price)) if asset.current_price is not None else Decimal('0')
        if not price.is_finite() or price <= 0 or not -30 <= (now - asset.last_updated).total_seconds() <= 300:
            raise PortfolioError('Market quote is stale or invalid')
        price = money(price)
        if price <= 0:
            raise PortfolioError('Market price is below supported precision')
        return price

    def tick(self, user_id, bot_id, revision, asset, signal=None, prediction_error=None, close=False):
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            config = self.repository.snapshot(row).config
            now = datetime.now(timezone.utc)
            if row['revision'] != revision:
                return {'status': 'configuration_changed'}
            if not close and (row['state'] != 'running' or not config.enabled or row['next_run_at'] > now):
                return {'status': 'inactive'}
            if close and row['state'] not in ('stopped', 'error'):
                raise PortfolioError('Stop the bot before closing its position', 409)
            if asset.symbol.upper() != config.symbol.split('/')[0]:
                raise PortfolioError('Quote does not match bot symbol')
            price = self.quote(asset, now)
            position = c.execute('SELECT * FROM trading_positions WHERE bot_id=%s', (bot_id,)).fetchone()
            reason, side, key = None, 'hold', None
            if position:
                if close:
                    reason = 'manual_close'
                elif position['stop_loss_price'] is not None and price <= position['stop_loss_price']:
                    reason = 'stop_loss'
                elif position['take_profit_price'] is not None and price >= position['take_profit_price']:
                    reason = 'take_profit'
                if reason:
                    side, key = 'sell', f"exit:{position['entry_order_id']}"
            elif close:
                return {'status': 'no_position'}
            if key is None:
                if prediction_error:
                    raise PortfolioError(prediction_error)
                if signal is None or signal.symbol != config.symbol or signal.expires_at <= now:
                    raise PortfolioError('A current matching prediction is required')
                side, key, reason = signal.signal.value, signal.event_key, 'prediction'
                if signal.confidence < config.confidence_threshold:
                    side, reason = 'hold', 'confidence_below_threshold'
                elif side == 'buy' and position:
                    side, reason = 'hold', 'position_already_open'
                elif side == 'sell' and not position:
                    side, reason = 'hold', 'no_position'
            existing = c.execute('SELECT * FROM trading_decisions WHERE bot_id=%s AND event_key=%s', (bot_id, key)).fetchone()
            if existing:
                self._success(c, bot_id, 'already_processed')
                return {'status': 'already_processed', 'decision': existing}
            order = None
            if side != 'hold':
                pending = c.execute("SELECT count(*) AS count FROM portfolio_orders WHERE portfolio_id=%s AND status='pending'",
                                    (config.portfolio_id,)).fetchone()['count']
                try:
                    if pending >= config.max_open_trades:
                        raise PortfolioError('Maximum bot open-trade limit reached')
                    quantity = position['quantity'] if side == 'sell' else config.order_amount
                    # A savepoint keeps a business rejection out of accounting.
                    with c.transaction():
                        order = self.executor.fill(c, row, config, key, side, quantity, price)
                        if side == 'buy':
                            stops = []
                            for pct, sign, fallback in ((config.stop_loss_pct, -1, order['stop_loss_price']),
                                                       (config.take_profit_pct, 1, order['take_profit_price'])):
                                stops.append(money(price * (1 + sign * pct / 100)) if pct is not None else fallback)
                            stop, take = stops
                            if stop is not None and not 0 < stop < price or take is not None and take <= price:
                                raise PortfolioError('Exit threshold is outside supported price precision')
                            c.execute('''INSERT INTO trading_positions(bot_id,quantity,entry_price,stop_loss_price,take_profit_price,entry_order_id)
                                VALUES (%s,%s,%s,%s,%s,%s)''', (bot_id, quantity, price, stop, take, order['order_id']))
                        else:
                            c.execute('DELETE FROM trading_positions WHERE bot_id=%s', (bot_id,))
                except PortfolioError as exc:
                    order, reason = None, str(exc)
                    # Retry protective exits on the next tick if funds are reserved.
                    if key.startswith('exit:'):
                        raise
            decision = c.execute('''INSERT INTO trading_decisions(bot_id,event_key,signal,reason,order_id)
                VALUES (%s,%s,%s,%s,%s) RETURNING *''',
                (bot_id, key, side, reason, order['order_id'] if order else None)).fetchone()
            self._success(c, bot_id, 'filled' if order else reason)
            return {'status': 'filled' if order else 'skipped', 'decision': decision, 'order': order}

    @staticmethod
    def _success(c, bot_id, result):
        c.execute('''UPDATE trading_bots SET failures=0,last_error=NULL,last_result=%s,last_tick_at=now(),
            next_run_at=now()+interval '30 seconds',updated_at=now() WHERE bot_id=%s''', (result, bot_id))

    def failure(self, user_id, bot_id, revision, message):
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if (row['revision'] != revision or row['state'] != 'running' or
                    row['next_run_at'] > datetime.now(timezone.utc)):
                return
            count = row['failures'] + 1
            c.execute('''UPDATE trading_bots SET failures=%s,last_error=%s,last_result='failed',last_tick_at=now(),
                state=%s,next_run_at=now()+(%s * interval '1 second'),updated_at=now() WHERE bot_id=%s''',
                (count, message, 'error' if count >= 5 else 'running', min(30 * 2 ** min(count-1, 4), 300), bot_id))
