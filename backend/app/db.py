from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema() -> None:
    """Добавляет новые колонки в уже существующую SQLite-базу."""
    try:
        insp = inspect(engine)
        if "snapshots" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("snapshots")}
        if "criteria" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE snapshots ADD COLUMN criteria JSON"))
    except Exception:
        return
