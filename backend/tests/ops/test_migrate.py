import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.ops.migrate import MIGRATIONS, run


@pytest.mark.skipif(not os.getenv("PREDICTION_TEST_DSN"), reason="Disposable PostgreSQL required")
def test_migrations_apply_once_and_reject_modified_history(tmp_path):
    base = os.environ["PREDICTION_TEST_DSN"]
    schema = "release_" + uuid4().hex
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    dsn = make_conninfo(base, options=f"-c search_path={schema}")
    try:
        run(directory=MIGRATIONS, dsn=dsn)
        run(directory=MIGRATIONS, dsn=dsn)
        with psycopg.connect(dsn) as conn:
            assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == len(list(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")))
            assert conn.execute("SELECT to_regclass('admin_audit')").fetchone()[0]
        files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
        for path in files:
            (tmp_path / path.name).write_bytes(path.read_bytes())
        (tmp_path / files[-1].name).write_text(files[-1].read_text() + "\n-- unexpected edit\n")
        with pytest.raises(RuntimeError, match="checksum changed"):
            run(directory=tmp_path, dsn=dsn)
    finally:
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
