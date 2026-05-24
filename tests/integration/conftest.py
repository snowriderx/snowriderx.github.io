"""
Integration test fixtures.
Uses Flask test client + real PostgreSQL DB.
Each test cleans up rows it created (prefix [TEST]).
"""
import os
import sys
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


# ── App fixture ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _flask_app():
    from admin import create_admin_app
    app = create_admin_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["RATELIMIT_ENABLED"] = False
    return app


@pytest.fixture
def client(_flask_app):
    with _flask_app.test_client() as c:
        yield c


# ── Auth helper ───────────────────────────────────────────────────────

@pytest.fixture
def authed_client(_flask_app, db_conn):
    """
    Test client với session của super-admin (IDU=1) pre-loaded.
    Hầu hết blueprints chỉ cho IDU=1 — dùng IDU=1 để test được tất cả.
    """
    with _flask_app.test_client() as c:
        cur = db_conn.cursor()
        # Ưu tiên IDU=1 (super admin), fallback sang user active đầu tiên
        cur.execute(
            'SELECT "IDU" FROM "tblUser" WHERE "IDU" = 1 AND "AcU" = 1 LIMIT 1'
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                'SELECT "IDU" FROM "tblUser" WHERE "AcU" = 1 LIMIT 1'
            )
            row = cur.fetchone()
        db_conn.rollback()
        if row is None:
            pytest.skip("No active admin user in DB")

        user_id = row[0]
        with _flask_app.app_context():
            from extensions import db
            from models.user import User
            if db.session.get(User, user_id) is None:
                pytest.skip("Cannot load admin user")
        with c.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True
        yield c


# ── DB fixture ────────────────────────────────────────────────────────

def _parse_pg_url(url: str) -> dict:
    """Parse postgresql://user:pass@host:port/dbname."""
    import re
    from urllib.parse import unquote
    m = re.match(
        r"postgresql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)",
        url,
    )
    if not m:
        raise ValueError(f"Cannot parse DATABASE_URL: {url!r}")
    user, pw, host, port, dbname = m.groups()
    return {
        "host": host,
        "port": int(port) if port else 5432,
        "user": user,
        "password": unquote(pw),
        "dbname": dbname,
    }


@pytest.fixture(scope="session")
def db_conn():
    """Direct psycopg2 connection for assertions and cleanup."""
    cfg = _parse_pg_url(os.environ["DATABASE_URL"])
    conn = psycopg2.connect(**cfg)
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def cleanup_test_rows(db_conn):
    """After each test, delete rows whose name starts with [TEST]."""
    yield
    cur = db_conn.cursor()
    queries = [
        "DELETE FROM \"tblPro\"  WHERE LEFT(\"NameP\", 6) = '[TEST]'",
        "DELETE FROM \"tblNews\" WHERE LEFT(\"NameN\", 6) = '[TEST]'",
        "DELETE FROM \"tblMenu\" WHERE LEFT(\"NameM\", 6) = '[TEST]'",
        "DELETE FROM \"tblAdvert\" WHERE LEFT(\"Title\", 6) = '[TEST]'",
        "DELETE FROM \"tblTag\"  WHERE LEFT(\"Title\", 6) = '[TEST]'",
        # tblLink rows left behind by product/news tests (slug conflicts next run)
        "DELETE FROM \"tblLink\" WHERE \"RowUrl\" LIKE 'test-%'",
        "DELETE FROM \"tblLink\" WHERE \"RowUrl\" LIKE 'tst-%'",
        "DELETE FROM \"tblLink\" WHERE \"RowUrl\" = 'edited'",
    ]
    for sql in queries:
        try:
            cur.execute(sql)
        except Exception:
            db_conn.rollback()
        else:
            db_conn.commit()
