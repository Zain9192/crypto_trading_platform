from collections.abc import Generator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from app.core.config import get_settings


def get_postgres_connection() -> Generator[Connection, None, None]:
    settings = get_settings()
    connection = psycopg.connect(settings.postgres_dsn, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()
