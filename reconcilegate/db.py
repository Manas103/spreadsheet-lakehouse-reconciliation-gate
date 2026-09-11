"""PostgreSQL publish/quarantine sink. PostgreSQL is not a managed
service in this environment; see the README for the stand-up commands.
Anything that touches this module catches the connection error and
reports "skipped, database unreachable" rather than failing the run,
matching this portfolio's serialized-product-traceability /
retail-sell-through-pipeline precedent.
"""
from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import Json

DEFAULT_CONFIG = {
    "host": os.environ.get("RECONCILEGATE_PG_HOST", "127.0.0.1"),
    "port": int(os.environ.get("RECONCILEGATE_PG_PORT", "5432")),
    "user": os.environ.get("RECONCILEGATE_PG_USER", "mvuser"),
    "password": os.environ.get("RECONCILEGATE_PG_PASSWORD", "mvpass"),
    "dbname": os.environ.get("RECONCILEGATE_PG_DATABASE", "reconcilegate"),
}

DDL = """
CREATE TABLE IF NOT EXISTS published_loads (
    load_id TEXT PRIMARY KEY,
    month INTEGER NOT NULL,
    n_sources INTEGER NOT NULL,
    published_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS quarantined_loads (
    load_id TEXT PRIMARY KEY,
    month INTEGER NOT NULL,
    failing_checks JSONB NOT NULL,
    quarantined_at TIMESTAMP NOT NULL DEFAULT now()
);
"""


def connect(config=None):
    cfg = config or DEFAULT_CONFIG
    return psycopg2.connect(**cfg)


def try_connect(config=None):
    """Returns a live connection, or None if PostgreSQL is unreachable."""
    try:
        return connect(config)
    except psycopg2.OperationalError:
        return None


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def publish(conn, load_id: str, month: int, n_sources: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO published_loads (load_id, month, n_sources) VALUES (%s, %s, %s) "
            "ON CONFLICT (load_id) DO NOTHING",
            (load_id, month, n_sources),
        )
    conn.commit()


def quarantine(conn, load_id: str, month: int, failing_checks: list) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO quarantined_loads (load_id, month, failing_checks) VALUES (%s, %s, %s) "
            "ON CONFLICT (load_id) DO NOTHING",
            (load_id, month, Json(failing_checks)),
        )
    conn.commit()


def reset(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE published_loads, quarantined_loads")
    conn.commit()
