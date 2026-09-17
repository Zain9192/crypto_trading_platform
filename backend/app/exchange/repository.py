import psycopg
from psycopg.rows import dict_row
from app.exchange.adapters import ExchangeFailure

PUBLIC_COLUMNS = 'connection_id,exchange,label,sandbox,read_only,created_at,updated_at'


class ExchangeRepository:
    def __init__(self, dsn):
        self.dsn = dsn

    def list(self, user_id):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            return c.execute(f'SELECT {PUBLIC_COLUMNS} FROM exchange_connections WHERE user_id=%s ORDER BY created_at,connection_id', (user_id,)).fetchall()

    def get(self, user_id, connection_id):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            row = c.execute('SELECT * FROM exchange_connections WHERE user_id=%s AND connection_id=%s', (user_id, connection_id)).fetchone()
        if row is None:
            raise ExchangeFailure('Exchange connection not found', 404)
        return row

    def create(self, user_id, connection_id, body, encrypted):
        try:
            with psycopg.connect(self.dsn, row_factory=dict_row) as c:
                return c.execute(f'''INSERT INTO exchange_connections
                    (connection_id,user_id,exchange,label,sandbox,credentials_ciphertext)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING {PUBLIC_COLUMNS}''',
                    (connection_id, user_id, body.exchange.value, body.label, body.sandbox, encrypted)).fetchone()
        except psycopg.errors.UniqueViolation:
            raise ExchangeFailure('A connection already exists for this exchange and environment', 409) from None

    def replace_credentials(self, user_id, connection_id, encrypted):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            self.require_idle(c, user_id, connection_id)
            row = c.execute(f'''UPDATE exchange_connections SET credentials_ciphertext=%s,updated_at=now()
                WHERE user_id=%s AND connection_id=%s RETURNING {PUBLIC_COLUMNS}''', (encrypted, user_id, connection_id)).fetchone()
        if row is None:
            raise ExchangeFailure('Exchange connection not found', 404)
        return row

    def delete(self, user_id, connection_id):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            self.require_idle(c, user_id, connection_id, deleting=True)
            row = c.execute('DELETE FROM exchange_connections WHERE user_id=%s AND connection_id=%s RETURNING connection_id', (user_id, connection_id)).fetchone()
        if row is None:
            raise ExchangeFailure('Exchange connection not found', 404)
        return {'message': 'Connection removed locally. Revoke its key at the exchange if no longer needed.'}

    @staticmethod
    def require_idle(c, user_id, connection_id, deleting=False):
        if not c.execute("SELECT to_regclass('sandbox_orders') AS present").fetchone()['present']:
            return
        if not c.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS acquired', (str(connection_id),)).fetchone()['acquired']:
            raise ExchangeFailure('Sandbox worker is using this connection; retry after stopping its bots', 409)
        owned = c.execute('SELECT 1 FROM exchange_connections WHERE connection_id=%s AND user_id=%s FOR UPDATE', (connection_id, user_id)).fetchone()
        if owned is None:
            raise ExchangeFailure('Exchange connection not found', 404)
        linked = c.execute('SELECT 1 FROM trading_bots WHERE connection_id=%s LIMIT 1', (connection_id,)).fetchone()
        if deleting and linked:
            raise ExchangeFailure('Connection has linked sandbox bots and cannot be removed', 409)
        active = c.execute("""SELECT 1 FROM trading_bots b WHERE connection_id=%s AND
            (state IN ('running','stopping') OR close_requested OR
             EXISTS (SELECT 1 FROM sandbox_positions p WHERE p.bot_id=b.bot_id AND p.quantity>0) OR
             EXISTS (SELECT 1 FROM sandbox_orders o WHERE o.bot_id=b.bot_id AND o.status IN ('submitting','unknown','open','partially_filled')))
            LIMIT 1""", (connection_id,)).fetchone()
        if active:
            raise ExchangeFailure('Stop bots, reconcile orders and close sandbox positions before replacing credentials', 409)

    def notify_failure(self, user_id, connection_id):
        with psycopg.connect(self.dsn) as c:
            c.execute('''INSERT INTO notifications(user_id,event_key,kind,payload)
                SELECT user_id,'exchange-read:' || connection_id || ':' || date_trunc('hour',now())::text,
                    'exchange_failure',jsonb_build_object('connection_id',connection_id,'symbol',exchange,
                    'message','Exchange account request failed. Review the connection and credentials before retrying.')
                FROM exchange_connections WHERE user_id=%s AND connection_id=%s
                ON CONFLICT(user_id,event_key) DO NOTHING''', (user_id,connection_id))
