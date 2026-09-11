from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.portfolio.risk import PortfolioError


class PostgresPortfolioRepository:
    def __init__(self, dsn):
        self.dsn = dsn

    @contextmanager
    def transaction(self):
        # A dedicated transaction, independent of the auth dependency's connection.
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            yield connection

    @staticmethod
    def owned(connection, user_id, portfolio_id):
        # Every write locks the parent first, including cancellation and settings.
        row = connection.execute(
            "SELECT * FROM portfolios WHERE portfolio_id=%s AND user_id=%s AND mode='paper' FOR UPDATE",
            (portfolio_id, user_id)).fetchone()
        if row is None:
            raise PortfolioError("Portfolio not found", 404)
        return row

    @staticmethod
    def state(connection, portfolio_id):
        holdings = connection.execute(
            "SELECT * FROM portfolio_holdings WHERE portfolio_id=%s ORDER BY symbol", (portfolio_id,)).fetchall()
        pending = connection.execute(
            "SELECT * FROM portfolio_orders WHERE portfolio_id=%s AND status='pending' ORDER BY created_at, order_id",
            (portfolio_id,)).fetchall()
        return holdings, pending
