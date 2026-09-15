from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.settings import settings

_connect_args = (
    {"check_same_thread": False} if settings.metadata_database_url.startswith("sqlite") else {}
)
engine = create_engine(
    settings.metadata_database_url, pool_pre_ping=True, future=True, connect_args=_connect_args
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all metadata-store models."""


def ensure_sqlite_schema() -> None:
    """SQLite has no separate migration story here — no install, no server, nothing
    to run Alembic against ahead of time (the Docker+Postgres path still uses Alembic
    normally; this only fires for a local `sqlite:///` URL, e.g. someone running the
    app without being able to install Postgres). Since a fresh local SQLite file has
    no prior data to preserve, creating the full current schema directly from the
    models is equivalent to "migrate to head" for this case.

    Must be called only after every model module has been imported (so each table is
    registered on `Base.metadata`) — `src.api.main` calls this right after
    `_mount_routers()`, which transitively imports every model. Calling it any
    earlier (e.g. at this module's own import time) risks running mid-import, before
    a model referenced by a foreign key has registered its table yet.
    """
    if engine.dialect.name != "sqlite":
        return
    Base.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
