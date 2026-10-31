"""Database helpers: engine factory, transaction context, truncate, batch insert."""

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

import config


def _build_url(database: str | None = None) -> URL:
    """Turn POSTGRES_CONFIG into a SQLAlchemy URL."""
    cfg = config.POSTGRES_CONFIG
    return URL.create(
        "postgresql+psycopg2",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
        database=database or cfg["dbname"],
    )


def get_engine(database: str | None = None) -> Engine:
    return create_engine(_build_url(database))


@contextmanager
def transaction(engine: Engine):
    with engine.begin() as conn:
        yield conn


def execute(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def truncate(conn, table: str) -> None:
    """Idempotency: wipe the table before reloading."""
    conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))