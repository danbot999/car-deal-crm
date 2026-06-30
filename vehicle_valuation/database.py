"""SQLAlchemy engine and session lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from .config import valuation_database_url
from .models import Base


DATABASE_URL = valuation_database_url()
CONNECT_ARGS = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
ENGINE_ARGS = {"connect_args": CONNECT_ARGS, "pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    ENGINE_ARGS.update({"poolclass": QueuePool, "pool_size": 1, "max_overflow": 0})
engine = create_engine(DATABASE_URL, **ENGINE_ARGS)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        migrate_sqlite_schema()


def migrate_sqlite_schema() -> None:
    """Additive migration for existing local indexes without discarding evidence."""
    additions = {
        "target_vehicles": {
            "field_confidence_json": "TEXT",
            "identity_key": "VARCHAR(300)",
            "search_id": "VARCHAR(32)",
        },
        "valuation_jobs": {
            "search_id": "VARCHAR(32)",
            "progress_stage": "VARCHAR(80) NOT NULL DEFAULT 'QUEUED'",
            "progress_json": "TEXT",
            "next_retry_at": "DATETIME",
        },
        "scrape_runs": {"search_id": "VARCHAR(32)"},
        "valuation_runs": {
            "search_id": "VARCHAR(32)",
            "coverage_json": "TEXT",
            "valuation_method": "VARCHAR(60)",
            "raw_median_cents": "INTEGER",
            "exact_comparable_count": "INTEGER NOT NULL DEFAULT 0",
            "adjustment_json": "TEXT",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
        for statement in (
            'CREATE INDEX IF NOT EXISTS "ix_target_identity_key" ON "target_vehicles" ("identity_key")',
            'CREATE INDEX IF NOT EXISTS "ix_target_search_id" ON "target_vehicles" ("search_id")',
            'CREATE INDEX IF NOT EXISTS "ix_job_search_id" ON "valuation_jobs" ("search_id")',
            'CREATE INDEX IF NOT EXISTS "ix_job_next_retry_at" ON "valuation_jobs" ("next_retry_at")',
            'CREATE INDEX IF NOT EXISTS "ix_scrape_search_id" ON "scrape_runs" ("search_id")',
            'CREATE INDEX IF NOT EXISTS "ix_valuation_search_id" ON "valuation_runs" ("search_id")',
        ):
            connection.execute(text(statement))


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
