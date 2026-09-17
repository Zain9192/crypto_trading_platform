from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, localcontext

import psycopg
from psycopg.rows import dict_row

from app.exchange.contracts import ConnectionPolicy
from app.exchange.service import configured_cipher, ExchangeService
from app.portfolio.risk import PortfolioError
from app.trading.execution import prediction_signal
from app.trading.orders import client_order_id
from app.trading.sandbox_adapter import SandboxAdapter, SubmissionRejected

ACTIVE = ('submitting', 'unknown', 'open', 'partially_filled')
ZERO = Decimal(0)
UNIT = Decimal('0.000000000000000001')


def ledger(value):
    return value.quantize(UNIT)


class SandboxEngine:
    def __init__(self, repository, settings, prediction, adapter_factory=SandboxAdapter):
        self.repository, self.settings, self.prediction = repository, settings, prediction
        self.adapter_factory = adapter_factory

    @contextmanager
    def account(self, row):
        # The session lock spans committed intents and network calls. A crash
        # releases it but leaves the intent durable for lookup, never resubmission.
        with psycopg.connect(self.repository.dsn, autocommit=True, row_factory=dict_row) as lock:
            acquired = lock.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired',
                                    (str(row['connection_id']),)).fetchone()['acquired']
            if not acquired:
                yield None
                return
            adapter = None
            try:
                with self.repository.transaction() as c:
                    connection = self.repository.sandbox_connection(c, row['user_id'], row['connection_id'])
                credentials = configured_cipher(self.settings).decrypt(connection['credentials_ciphertext'], **ExchangeService.context(connection))
                adapter = self.adapter_factory(credentials, ConnectionPolicy(sandbox=True, read_only=False))
                yield adapter
            finally:
                if adapter is not None:
                    adapter.close()
                lock.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (str(row['connection_id']),))

    def run(self, original):
        with self.account(original) as adapter:
            if adapter is None:
                return
            row = self.repository.get(original['user_id'], original['bot_id'])
            config = self.repository.snapshot(row).config
            with self.repository.transaction() as c:
                outstanding = c.execute('SELECT * FROM sandbox_orders WHERE connection_id=%s AND status=ANY(%s) ORDER BY created_at LIMIT 1',
                                        (config.connection_id, list(ACTIVE))).fetchone()
            if outstanding:
                if outstanding['bot_id'] == row['bot_id'] and outstanding['next_reconcile_at'] <= datetime.now(timezone.utc):
                    self.reconcile(row, outstanding, adapter)
                else:
                    with self.repository.transaction() as c:
                        c.execute("UPDATE trading_bots SET next_run_at=now()+interval '15 seconds' WHERE bot_id=%s", (row['bot_id'],))
                return
            if row['state'] == 'stopping':
                with self.repository.transaction() as c:
                    self.repository.locked(c, row['user_id'], row['bot_id'])
                    c.execute("UPDATE trading_bots SET state='stopped',updated_at=now() WHERE bot_id=%s AND state='stopping'", (row['bot_id'],))
                return
            if not row['close_requested'] and (row['state'] != 'running' or not config.enabled):
                return
            quote = adapter.get_price(config.symbol)
            now = datetime.now(timezone.utc)
            if quote.observed_at.tzinfo is None or not -30 <= (now-quote.observed_at).total_seconds() <= 60:
                raise PortfolioError('Sandbox quote is stale')
            with self.repository.transaction() as c:
                c.execute('UPDATE trading_bots SET last_price=%s,price_observed_at=%s WHERE bot_id=%s', (quote.price, quote.observed_at, row['bot_id']))
            position = row['position']
            side, event_key, reason = None, None, None
            prediction_expiry = None
            if position:
                if row['close_requested']:
                    reason = 'manual_close'
                elif position['stop_loss_price'] is not None and quote.price <= position['stop_loss_price']:
                    reason = 'stop_loss'
                elif position['take_profit_price'] is not None and quote.price >= position['take_profit_price']:
                    reason = 'take_profit'
                if reason:
                    side = 'sell'
                    # Each confirmed IOC remainder is a new attempt; an uncertain
                    # attempt blocks this path until it has been reconciled.
                    with self.repository.transaction() as c:
                        n = c.execute("SELECT count(*) AS n FROM sandbox_orders WHERE bot_id=%s AND side='sell'", (row['bot_id'],)).fetchone()['n']
                    event_key = f"exit:{position['entry_order_id']}:{n}"
            elif row['close_requested']:
                with self.repository.transaction() as c:
                    c.execute('UPDATE trading_bots SET close_requested=false WHERE bot_id=%s', (row['bot_id'],))
                return
            if side is None:
                forecast = self.prediction.predict(config.symbol.split('/')[0], config.interval)
                if forecast.quote_asset != 'USDT':
                    raise PortfolioError('Sandbox predictions must use USDT candles')
                signal = prediction_signal(config, forecast, datetime.now(timezone.utc))
                side, event_key, reason = signal.signal.value, signal.event_key, 'prediction'
                prediction_expiry = signal.expires_at
                if signal.confidence < config.confidence_threshold:
                    side, reason = 'hold', 'confidence_below_threshold'
                elif side == 'buy' and position:
                    side, reason = 'hold', 'position_already_open'
                elif side == 'sell' and not position:
                    side, reason = 'hold', 'no_position'
            balances = adapter.get_balance()
            self.save_balances(config.connection_id, balances)
            request = None
            if side != 'hold':
                amount = position['quantity'] if side == 'sell' else config.order_amount
                request = adapter.prepare(client_order_id(row['bot_id'], event_key), config.symbol, side, amount, quote.price, config.slippage_bps)
            with self.repository.transaction() as c:
                current, _ = self.repository.locked(c, row['user_id'], row['bot_id'])
                if current['revision'] != row['revision'] or (not current['close_requested'] and current['state'] != 'running'):
                    return
                if c.execute('SELECT 1 FROM trading_decisions WHERE bot_id=%s AND event_key=%s', (row['bot_id'], event_key)).fetchone():
                    self.success(c, row['bot_id'], 'already_processed')
                    return
                if prediction_expiry is not None and prediction_expiry <= datetime.now(timezone.utc):
                    raise PortfolioError('Prediction expired before reservation')
                if request:
                    try:
                        self.risk(c, config, request, balances, quote.observed_at)
                    except PortfolioError as exc:
                        if reason != 'prediction':
                            raise
                        side, reason, request = 'hold', str(exc), None
                c.execute('INSERT INTO trading_decisions(bot_id,event_key,signal,reason) VALUES (%s,%s,%s,%s)',
                          (row['bot_id'], event_key, side, reason))
                if request:
                    c.execute('''INSERT INTO sandbox_orders(order_id,bot_id,connection_id,event_key,symbol,side,amount,limit_price)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (request.client_order_id, row['bot_id'], config.connection_id, event_key, config.symbol, side, request.amount, request.price))
                if request:
                    c.execute("UPDATE trading_bots SET last_result='submitting',last_tick_at=now(),next_run_at=now()+interval '30 seconds' WHERE bot_id=%s", (row['bot_id'],))
                else:
                    self.success(c, row['bot_id'], reason)
            if request:
                def approved(candidate):
                    if candidate != request:
                        raise PortfolioError('Order differs from reserved intent')
                adapter.risk_check = approved
                # From this point every failure is ambiguous, including process
                # termination. The only recovery path is client-ID lookup.
                try:
                    adapter.submit(request)
                except SubmissionRejected:
                    with self.repository.transaction() as c:
                        self.repository.locked(c, row['user_id'], row['bot_id'])
                        c.execute("UPDATE sandbox_orders SET status='rejected',last_error='Exchange rejected submission',updated_at=now() WHERE order_id=%s", (request.client_order_id,))
                        c.execute("UPDATE trading_bots SET state=CASE WHEN state='stopping' THEN 'stopped' ELSE state END WHERE bot_id=%s", (row['bot_id'],))
                        self.unfilled(c, row['bot_id'], 'rejected')
                    return
                except Exception:
                    pass
                with self.repository.transaction() as c:
                    order = c.execute('SELECT * FROM sandbox_orders WHERE order_id=%s', (request.client_order_id,)).fetchone()
                self.reconcile(row, order, adapter)

    @staticmethod
    def risk(c, config, request, balances, observed_at):
        if not -30 <= (datetime.now(timezone.utc)-observed_at).total_seconds() <= 60:
            raise PortfolioError('Quote expired before submission')
        if c.execute('SELECT 1 FROM sandbox_orders WHERE connection_id=%s AND status=ANY(%s)', (config.connection_id, list(ACTIVE))).fetchone():
            raise PortfolioError('Reconcile the outstanding account order first')
        free = {b.currency: b.free for b in balances}
        base, quote = config.symbol.split('/')
        cost = request.amount * request.price
        if request.side == 'buy':
            if not config.min_quote_per_order <= cost <= config.max_quote_per_order:
                raise PortfolioError('Order value is outside configured quote-currency limits')
            if free.get(quote, ZERO) < cost * Decimal('1.01'):
                raise PortfolioError('Insufficient sandbox quote balance including 1% fee reserve')
            count = c.execute('''SELECT count(*) AS n FROM sandbox_positions p JOIN trading_bots b USING(bot_id)
                WHERE b.connection_id=%s AND p.quantity>0''', (config.connection_id,)).fetchone()['n']
            if count >= config.max_open_positions:
                raise PortfolioError('Maximum sandbox positions reached')
        elif free.get(base, ZERO) < request.amount:
            raise PortfolioError('Insufficient sandbox base-asset balance')
        # One unresolved order per account is stricter than max_open_trades>=1.

    def reconcile(self, row, order, adapter):
        try:
            remote = adapter.lookup(order['order_id'], order['symbol'])
            if remote['side'] != order['side'] or remote['amount'] != order['amount']:
                raise PortfolioError('Exchange order does not match the stored intent')
            if remote['status'] in ('NEW', 'PARTIALLY_FILLED', 'PENDING_CANCEL'):
                # IOC orders should not remain open. Cancellation is safe to
                # retry; submission is never retried.
                try:
                    adapter.cancel(order['order_id'], order['symbol'])
                except Exception:
                    pass
                remote = adapter.lookup(order['order_id'], order['symbol'])
            fills = adapter.fills(remote, order['symbol']) if remote['filled'] else []
            self.apply(row, order, remote, fills)
            try:
                self.save_balances(row['connection_id'], adapter.get_balance())
            except Exception:
                pass  # Last observed balance remains explicitly timestamped.
        except Exception:
            with self.repository.transaction() as c:
                self.repository.locked(c, row['user_id'], row['bot_id'])
                current = c.execute('SELECT * FROM sandbox_orders WHERE order_id=%s', (order['order_id'],)).fetchone()
                n = current['attempts'] + 1
                message = 'Order outcome is unresolved; submission will not be repeated. Reconciliation continues.'
                c.execute('''UPDATE sandbox_orders SET status='unknown',attempts=%s,last_error=%s,
                    next_reconcile_at=now()+(%s * interval '1 second'),updated_at=now() WHERE order_id=%s''',
                    (n, message, min(15*2**min(n-1,5),300), order['order_id']))
                c.execute('''UPDATE trading_bots SET last_error=%s,last_result='reconciliation_required',
                    next_run_at=now()+interval '15 seconds',updated_at=now() WHERE bot_id=%s''', (message, row['bot_id']))

    def apply(self, row, order, remote, fills):
        statuses = {'NEW': 'open', 'PARTIALLY_FILLED': 'partially_filled', 'FILLED': 'filled',
                    'CANCELED': 'cancelled', 'REJECTED': 'rejected', 'EXPIRED': 'expired', 'EXPIRED_IN_MATCH': 'expired'}
        status = statuses.get(remote['status'], 'unknown')
        with localcontext() as ctx, self.repository.transaction() as c:
            ctx.prec = 60
            current, _ = self.repository.locked(c, row['user_id'], row['bot_id'])
            config = self.repository.snapshot(current).config
            stored = c.execute('SELECT * FROM sandbox_orders WHERE order_id=%s FOR UPDATE', (order['order_id'],)).fetchone()
            if (remote['side'] != stored['side'] or remote['amount'] != stored['amount'] or
                    remote['filled'] < stored['filled'] or remote['filled'] > stored['amount'] or
                    remote['cost'] < stored['cost'] or remote['filled'] == 0 and remote['cost'] != 0 or
                    status == 'filled' and remote['filled'] != stored['amount']):
                raise PortfolioError('Exchange fill totals moved backwards or exceed the order')
            c.execute('INSERT INTO sandbox_positions(bot_id) VALUES (%s) ON CONFLICT DO NOTHING', (row['bot_id'],))
            p = c.execute('SELECT * FROM sandbox_positions WHERE bot_id=%s', (row['bot_id'],)).fetchone()
            base, quote = order['symbol'].split('/')
            for fill in fills:
                inserted = c.execute('''INSERT INTO sandbox_fills(connection_id,symbol,trade_id,order_id,quantity,price,cost,fee,fee_currency,executed_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING trade_id''',
                    (row['connection_id'], order['symbol'], fill['trade_id'], order['order_id'], fill['quantity'], fill['price'],
                     fill['cost'], fill['fee'], fill['fee_currency'], fill['executed_at'])).fetchone()
                if not inserted:
                    continue
                base_fee = fill['fee'] if fill['fee_currency'] == base else ZERO
                quote_fee = fill['fee'] if fill['fee_currency'] == quote else ZERO
                if order['side'] == 'buy':
                    quantity = fill['quantity'] - base_fee
                    if quantity <= 0:
                        raise PortfolioError('Invalid net fill quantity')
                    p['quantity'] += quantity
                    p['cost_basis'] += fill['cost'] + quote_fee
                    p['entry_order_id'] = order['order_id']
                    average = p['cost_basis'] / p['quantity']
                    p['stop_loss_price'] = ledger(average*(1-config.stop_loss_pct/100)) if config.stop_loss_pct is not None else None
                    p['take_profit_price'] = ledger(average*(1+config.take_profit_pct/100)) if config.take_profit_pct is not None else None
                else:
                    quantity = fill['quantity'] + base_fee
                    if quantity > p['quantity']:
                        raise PortfolioError('Exchange sale exceeds the managed position')
                    basis = p['cost_basis'] if quantity == p['quantity'] else ledger(p['cost_basis'] * quantity/p['quantity'])
                    p['quantity'] -= quantity
                    p['cost_basis'] -= basis
                    p['realized_pnl'] += fill['cost'] - quote_fee - basis
                c.execute('''UPDATE sandbox_positions SET quantity=%s,cost_basis=%s,realized_pnl=%s,entry_order_id=%s,
                    stop_loss_price=%s,take_profit_price=%s,updated_at=now() WHERE bot_id=%s''',
                    (p['quantity'], p['cost_basis'], p['realized_pnl'], p['entry_order_id'], p['stop_loss_price'], p['take_profit_price'], row['bot_id']))
            totals = c.execute('SELECT COALESCE(sum(quantity),0) AS quantity,COALESCE(sum(cost),0) AS cost FROM sandbox_fills WHERE order_id=%s', (order['order_id'],)).fetchone()
            if totals['quantity'] != remote['filled'] or totals['cost'] != remote['cost']:
                raise PortfolioError('Persisted fills do not match exchange totals')
            c.execute('''UPDATE sandbox_orders SET status=%s,exchange_order_id=%s,filled=%s,cost=%s,
                last_error=NULL,attempts=0,next_reconcile_at=now()+interval '15 seconds',updated_at=now() WHERE order_id=%s''',
                (status, remote['exchange_order_id'], remote['filled'], remote['cost'], order['order_id']))
            if status not in ACTIVE:
                if current['state'] == 'stopping':
                    c.execute("UPDATE trading_bots SET state='stopped',revision=revision+1 WHERE bot_id=%s", (row['bot_id'],))
                if p['quantity'] == 0:
                    c.execute('UPDATE trading_bots SET close_requested=false WHERE bot_id=%s', (row['bot_id'],))
            if status not in ACTIVE and remote['filled'] == 0:
                self.unfilled(c, row['bot_id'], status)
            else:
                self.success(c, row['bot_id'], status)

    @staticmethod
    def unfilled(c, bot_id, status):
        c.execute("""UPDATE trading_bots SET failures=failures+1,last_result=%s,
            last_error='Sandbox order had no fills; execution pauses after five consecutive attempts',
            state=CASE WHEN failures>=4 AND state='running' THEN 'error' ELSE state END,
            close_requested=CASE WHEN failures>=4 THEN false ELSE close_requested END,
            last_tick_at=now(),next_run_at=now()+interval '60 seconds',updated_at=now() WHERE bot_id=%s""", (status, bot_id))

    @staticmethod
    def success(c, bot_id, result):
        c.execute('''UPDATE trading_bots SET failures=0,last_error=NULL,last_result=%s,last_tick_at=now(),
            next_run_at=now()+interval '30 seconds',updated_at=now() WHERE bot_id=%s''', (result, bot_id))

    def save_balances(self, connection_id, balances):
        with self.repository.transaction() as c:
            c.execute('DELETE FROM sandbox_balances WHERE connection_id=%s', (connection_id,))
            for b in balances:
                c.execute('INSERT INTO sandbox_balances(connection_id,currency,free,used,total) VALUES (%s,%s,%s,%s,%s)',
                          (connection_id,b.currency,b.free,b.used,b.total))

    def failure(self, user_id, bot_id, revision, message):
        with self.repository.transaction() as c:
            row, _ = self.repository.locked(c, user_id, bot_id)
            if row['revision'] != revision:
                return
            count = row['failures'] + 1
            c.execute("""UPDATE trading_bots SET failures=%s,last_error=%s,last_result='failed',last_tick_at=now(),
                state=CASE WHEN %s>=5 AND state='running' THEN 'error' ELSE state END,
                close_requested=CASE WHEN %s>=5 THEN false ELSE close_requested END,
                next_run_at=now()+(%s * interval '1 second'),updated_at=now() WHERE bot_id=%s""",
                (count, message, count, count, min(30*2**min(count-1,4),300), bot_id))
