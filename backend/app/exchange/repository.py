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
            row = c.execute(f'''UPDATE exchange_connections SET credentials_ciphertext=%s,updated_at=now()
                WHERE user_id=%s AND connection_id=%s RETURNING {PUBLIC_COLUMNS}''', (encrypted, user_id, connection_id)).fetchone()
        if row is None:
            raise ExchangeFailure('Exchange connection not found', 404)
        return row

    def delete(self, user_id, connection_id):
        with psycopg.connect(self.dsn) as c:
            row = c.execute('DELETE FROM exchange_connections WHERE user_id=%s AND connection_id=%s RETURNING connection_id', (user_id, connection_id)).fetchone()
        if row is None:
            raise ExchangeFailure('Exchange connection not found', 404)
        return {'message': 'Connection removed locally. Revoke its key at the exchange if no longer needed.'}
