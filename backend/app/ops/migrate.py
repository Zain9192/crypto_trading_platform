"""Transactional, checksum-checked PostgreSQL migrations for releases."""
import argparse
from hashlib import sha256
from pathlib import Path

import psycopg

from app.core.config import get_settings

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "postgres"
if not MIGRATIONS.exists():
    MIGRATIONS = Path(__file__).resolve().parents[3] / "database" / "postgres"
LOCK_ID = 74239011


def run(baseline=False, directory=MIGRATIONS, dsn=None):
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("No migrations found in the release image")
    with psycopg.connect(dsn or get_settings().postgres_dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            existed = conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]
            if not existed and conn.execute("SELECT to_regclass('users')").fetchone()[0]:
                if not baseline:
                    raise RuntimeError("Existing schema requires reviewed migration baseline")
                required = ('users', 'portfolio_orders', 'exchange_connections', 'sandbox_orders',
                            'notification_email_outbox', 'admin_audit')
                if any(conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0] is None
                       for name in required):
                    raise RuntimeError("Existing schema is incomplete; cannot baseline")
            elif baseline:
                raise RuntimeError("Baseline is only for an existing, untracked Phase 9 schema")
            conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY, checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
            applied = dict(conn.execute("SELECT name,checksum FROM schema_migrations").fetchall())
            known = {path.name for path in files}
            if set(applied) - known:
                raise RuntimeError("Database has migrations absent from this release")
            for path in files:
                content = path.read_bytes()
                checksum = sha256(content).hexdigest()
                if path.name in applied:
                    if applied[path.name].strip() != checksum:
                        raise RuntimeError(f"Migration checksum changed: {path.name}")
                    continue
                with conn.transaction():
                    if not baseline:
                        conn.execute(content.decode("utf-8"))
                    conn.execute("INSERT INTO schema_migrations(name,checksum) VALUES (%s,%s)",
                                 (path.name, checksum))
                print(f"Recorded migration {path.name}")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    run(baseline=args.baseline)


if __name__ == "__main__":
    main()
