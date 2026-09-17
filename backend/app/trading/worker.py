import logging
import signal
import threading
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.prediction.dependencies import get_prediction_service
from app.trading.engine import TradingEngine
from app.trading.execution import prediction_signal
from app.trading.repository import TradingRepository
from app.trading.sandbox import SandboxEngine

logger = logging.getLogger(__name__)


def main():
    repository = TradingRepository(get_settings().postgres_dsn)
    market = get_market_service()
    prediction = get_prediction_service(market)
    engine = TradingEngine(repository)
    sandbox = SandboxEngine(repository, get_settings(), prediction)
    stopped = threading.Event()
    for kind in (signal.SIGINT, signal.SIGTERM):
        signal.signal(kind, lambda *_: stopped.set())
    worker_id = str(uuid4())
    while not stopped.is_set():
        try:
            with repository.transaction() as c:
                c.execute('''INSERT INTO trading_worker_heartbeat(worker_id) VALUES (%s)
                    ON CONFLICT(worker_id) DO UPDATE SET seen_at=now()''', (worker_id,))
                c.execute("DELETE FROM trading_worker_heartbeat WHERE seen_at < now()-interval '1 day'")
                rows = c.execute("""SELECT * FROM trading_bots b WHERE next_run_at<=now() AND
                    (state IN ('running','stopping') OR close_requested OR EXISTS
                     (SELECT 1 FROM sandbox_orders o WHERE o.bot_id=b.bot_id AND o.status IN ('submitting','unknown','open','partially_filled')))
                    ORDER BY next_run_at LIMIT 20""").fetchall()
            for row in rows:
                if stopped.is_set():
                    break
                try:
                    if row['connection_id'] is not None:
                        sandbox.run(row)
                        continue
                    config = repository.snapshot(row).config
                    asset = market.get_asset(config.symbol.split('/')[0])
                    if asset is None:
                        raise ValueError('Missing quote')
                    # Fetching a model must never prevent an already triggered exit.
                    protected = repository.get(row['user_id'], row['bot_id'])['position']
                    price = engine.quote(asset, datetime.now(timezone.utc))
                    exit_due = protected and (
                        protected['stop_loss_price'] is not None and price <= protected['stop_loss_price'] or
                        protected['take_profit_price'] is not None and price >= protected['take_profit_price'])
                    trade_signal, error = None, None
                    if not exit_due:
                        try:
                            forecast = prediction.predict(config.symbol.split('/')[0], config.interval)
                            trade_signal = prediction_signal(config, forecast, datetime.now(timezone.utc))
                        except Exception:
                            error = 'Prediction unavailable; check active model and fresh candle history'
                    engine.tick(row['user_id'], row['bot_id'], row['revision'], asset, trade_signal, error)
                except Exception:
                    # Provider/DB exception text can contain sensitive connection details.
                    logger.warning('Bot tick failed: %s', row['bot_id'])
                    failure = sandbox.failure if row['connection_id'] else engine.failure
                    failure(row['user_id'], row['bot_id'], row['revision'],
                                   'Execution unavailable; check market data, model and storage. Reset after five failures.')
        except Exception:
            logger.warning('Trading worker storage unavailable; retrying')
        stopped.wait(5)
    with repository.transaction() as c:
        c.execute('DELETE FROM trading_worker_heartbeat WHERE worker_id=%s', (worker_id,))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
