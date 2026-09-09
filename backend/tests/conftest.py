import os

os.environ.setdefault(
    "METADATA_DATABASE_URL",
    "postgresql+psycopg://viewbuilder:viewbuilder_dev@localhost:5434/viewbuilder_metadata",
)

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.main import app
from src.db.session import SessionLocal, engine
from src.models.connection_config import ConnectionConfig


def _postgres_reachable() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_reachable(), reason="metadata-store Postgres is not reachable in this environment"
)


@pytest.fixture
def db_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        # Clean up rows created during the test so tests don't leak state into each other.
        session.execute(text("DELETE FROM run_log_entry"))
        session.execute(text("DELETE FROM mapping_version"))
        session.execute(text("DELETE FROM mapping_definition"))
        session.execute(text("DELETE FROM enum_translation_version"))
        session.execute(text("DELETE FROM enum_translation_table"))
        session.execute(text("DELETE FROM connection_config"))
        session.commit()
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_connection(db_session) -> ConnectionConfig:
    os.environ["VIEWBUILDER_CRED_TESTCRED"] = "test-password"
    connection = ConnectionConfig(
        id=uuid.uuid4(),
        name=f"test-connection-{uuid.uuid4().hex[:8]}",
        role="either",
        environment="dev",
        host="localhost",
        port=1433,
        database="viewbuilder_legacy",
        credential_ref="testcred",
    )
    db_session.add(connection)
    db_session.commit()
    db_session.refresh(connection)
    return connection
