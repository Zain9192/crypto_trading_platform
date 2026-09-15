"""Offline atomic re-encryption. Stop credential writers before running."""
import base64
import os
import psycopg
from psycopg.rows import dict_row
from app.core.config import get_settings
from app.exchange.security import CredentialCipher
from app.exchange.service import ExchangeService


def rotate(dsn, old_key, new_key):
    old, new = CredentialCipher(old_key), CredentialCipher(new_key)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        rows = c.execute('SELECT * FROM exchange_connections ORDER BY connection_id FOR UPDATE').fetchall()
        for row in rows:
            context = ExchangeService.context(row)
            credentials = old.decrypt(row['credentials_ciphertext'], **context)
            c.execute('UPDATE exchange_connections SET credentials_ciphertext=%s,updated_at=now() WHERE connection_id=%s',
                      (new.encrypt(credentials, **context), row['connection_id']))
    return len(rows)


def main():
    try:
        old = base64.b64decode(os.environ['EXCHANGE_OLD_ENCRYPTION_KEY'], altchars=b'-_', validate=True)
        new = base64.b64decode(os.environ['EXCHANGE_NEW_ENCRYPTION_KEY'], altchars=b'-_', validate=True)
        count = rotate(get_settings().postgres_dsn, old, new)
    except (ValueError, KeyError, psycopg.Error):
        raise SystemExit('Rotation failed; transaction rolled back. Check configuration.') from None
    print(f'Re-encrypted {count} connections. Configure the new key before restarting writers.')


if __name__ == '__main__':
    main()
