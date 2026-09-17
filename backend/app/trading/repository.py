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
        # Paper writes lock the portfolio; sandbox writes lock the exchange account first.
        portfolio = (self.owned(c, user_id, row['portfolio_id']) if row['portfolio_id'] is not None
                     else self.sandbox_connection(c, user_id, row['connection_id']))
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
            if row['connection_id'] is None:
                row['position'] = c.execute('SELECT * FROM trading_positions WHERE bot_id=%s', (bot_id,)).fetchone()
            else:
                row['position'] = c.execute('''SELECT *, CASE WHEN quantity>0 THEN cost_basis/quantity ELSE 0 END AS entry_price
                    FROM sandbox_positions WHERE bot_id=%s AND quantity>0''', (bot_id,)).fetchone()
                if row['position'] and row['last_price'] is not None:
                    row['position']['unrealized_pnl'] = row['position']['quantity'] * row['last_price'] - row['position']['cost_basis']
                row['sandbox_orders'] = c.execute('SELECT * FROM sandbox_orders WHERE bot_id=%s ORDER BY created_at DESC LIMIT 25', (bot_id,)).fetchall()
                row['balances'] = c.execute('SELECT * FROM sandbox_balances WHERE connection_id=%s ORDER BY currency', (row['connection_id'],)).fetchall()
                row['realized_pnl'] = c.execute('SELECT realized_pnl FROM sandbox_positions WHERE bot_id=%s', (bot_id,)).fetchone()
                row['fees'] = c.execute('''SELECT f.fee_currency,sum(f.fee) AS amount FROM sandbox_fills f
                    JOIN sandbox_orders o USING(order_id) WHERE o.bot_id=%s GROUP BY f.fee_currency''', (bot_id,)).fetchall()
            return row

    def create(self, user_id, config):
        with self.transaction() as c:
            if config.mode == 'sandbox':
                self.sandbox_connection(c, user_id, config.connection_id)
                existing = c.execute('SELECT bot_id FROM trading_bots WHERE connection_id=%s AND symbol=%s',
                                     (config.connection_id, config.symbol)).fetchone()
                if existing:
                    raise PortfolioError('A sandbox bot already exists for this connection and symbol', 409)
                return c.execute('''INSERT INTO trading_bots(bot_id,user_id,connection_id,symbol,config)
                    VALUES (%s,%s,%s,%s,%s) RETURNING *''',
                    (uuid4(), user_id, config.connection_id, config.symbol, Jsonb(config.model_dump(mode='json')))).fetchone()
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
            rows = c.execute('''SELECT d.*,COALESCE(o.status,s.status) AS order_status,COALESCE(o.quantity,s.filled) AS quantity,
                COALESCE(o.simulation_price,s.cost/NULLIF(s.filled,0)) AS simulation_price,o.fee
                FROM trading_decisions d LEFT JOIN portfolio_orders o USING(order_id)
                LEFT JOIN sandbox_orders s ON s.bot_id=d.bot_id AND s.event_key=d.event_key
                WHERE d.bot_id=%s AND (%s::bigint IS NULL OR d.decision_id < %s)
                ORDER BY d.decision_id DESC LIMIT %s''', (bot_id, before, before, limit + 1)).fetchall()
            return {'items': rows[:limit], 'next_cursor': rows[limit-1]['decision_id'] if len(rows)>limit else None}

    @staticmethod
    def sandbox_connection(c, user_id, connection_id):
        row = c.execute("""SELECT * FROM exchange_connections WHERE connection_id=%s AND user_id=%s
            AND exchange='binance' AND sandbox=true FOR UPDATE""", (connection_id, user_id)).fetchone()
        if row is None:
            raise PortfolioError('A Binance Spot Testnet connection owned by this account is required', 404)
        return row

    @staticmethod
    def unresolved(c, bot_id):
        return c.execute("""SELECT * FROM sandbox_orders WHERE bot_id=%s
            AND status IN ('submitting','unknown','open','partially_filled') ORDER BY created_at""", (bot_id,)).fetchall()
