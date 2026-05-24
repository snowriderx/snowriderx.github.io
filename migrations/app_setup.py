"""Shared DB connection helper for migration/seed scripts."""
import os
import re
from urllib.parse import unquote


def get_db_conn():
    import psycopg2
    url = os.environ["DATABASE_URL"]
    m = re.match(
        r"postgresql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)", url
    )
    if not m:
        raise ValueError(f"Cannot parse DATABASE_URL: {url!r}")
    user, pw, host, port, dbname = m.groups()
    return psycopg2.connect(
        host=host,
        port=int(port) if port else 5432,
        user=user,
        password=unquote(pw),
        dbname=dbname,
    )
