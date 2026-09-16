from uuid import uuid4

from psycopg.types.json import Jsonb

from app.portfolio.repository import PostgresPortfolioRepository
from app.portfolio.risk import PortfolioError
from app.trading.contracts import BotConfig, BotSnapshot


class TradingRepository(PostgresPortfolioRepository):
    @staticmethod
    def snapshot(row):
        return BotSnapshot(bot_id=row['bot_id'], config=BotConfig.model_validate(row['config']), state=row['state'])

    @staticmethod
    def find(c, user_id, bot_id):
        row = c.execute('SELECT * FROM trading_bots WHERE bot_id=%s AND user_id=%s', (bot_id, user_id)).fetchone()
        if row is None:
            raise PortfolioError('Bot not found', 404)
        return row

    def locked(self, c, user_id, bot_id):
        row = self.find(c, user_id, bot_id)
        # All accounting and bot writes acquire the portfolio lock first.
        portfolio = self.owned(c, user_id, row['portfolio_id'])
        row = c.execute('SELECT * FROM trading_bots WHERE bot_id=%s AND user_id=%s FOR UPDATE', (bot_id, user_id)).fetchone()
        if row is None:
            raise PortfolioError('Bot not found', 404)
        return row, portfolio

    def list(self, user_id):
        with self.transaction() as c:
            return c.execute('SELECT * FROM trading_bots WHERE user_id=%s ORDER BY created_at DESC', (user_id,)).fetchall()

    def get(self, user_id, bot_id):
        with self.transaction() as c:
            row = self.find(c, user_id, bot_id)
            row['position'] = c.execute('SELECT * FROM trading_positions WHERE bot_id=%s', (bot_id,)).fetchone()
            return row

    def create(self, user_id, config):
        with self.transaction() as c:
            self.owned(c, user_id, config.portfolio_id)
            existing = c.execute('SELECT bot_id FROM trading_bots WHERE portfolio_id=%s AND symbol=%s',
                                 (config.portfolio_id, config.symbol)).fetchone()
            if existing:
                raise PortfolioError('A bot already exists for this portfolio and symbol', 409)
            return c.execute('''INSERT INTO trading_bots(bot_id,user_id,portfolio_id,symbol,config)
                VALUES (%s,%s,%s,%s,%s) RETURNING *''',
                (uuid4(), user_id, config.portfolio_id, config.symbol, Jsonb(config.model_dump(mode='json')))).fetchone()

    def history(self, user_id, bot_id, before=None, limit=25):
        with self.transaction() as c:
            self.find(c, user_id, bot_id)
            rows = c.execute('''SELECT d.*,o.status AS order_status,o.quantity,o.simulation_price,o.fee
                FROM trading_decisions d LEFT JOIN portfolio_orders o USING(order_id)
                WHERE d.bot_id=%s AND (%s::bigint IS NULL OR d.decision_id < %s)
                ORDER BY d.decision_id DESC LIMIT %s''', (bot_id, before, before, limit + 1)).fetchall()
            return {'items': rows[:limit], 'next_cursor': rows[limit-1]['decision_id'] if len(rows)>limit else None}
