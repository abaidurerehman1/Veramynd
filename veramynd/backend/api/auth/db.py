"""SQLAlchemy engine / session for Veramynd auth + dashboard metadata."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        cfg = settings()
        _engine = create_engine(
            str(cfg["database_url"]),
            pool_pre_ping=True,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def SessionLocal() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so metadata is populated.
    from . import models  # noqa: F401
    from sqlalchemy import text

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    # Lightweight column add for existing DBs (no migration runner).
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512)"))
