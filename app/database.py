from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


def creer_engine(url: str):
    # timeout : sous SQLite, une écriture concurrente attend le verrou au lieu d'échouer.
    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = creer_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def maintenant() -> datetime:
    """Heure UTC sans fuseau (SQLite ne conserve pas le fuseau)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
