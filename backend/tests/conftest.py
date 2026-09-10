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
from src.models.legacy_shape import LegacyShapeCapture


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
        # `current_version_id` FKs (mapping_definition -> mapping_version,
        # enum_translation_table -> enum_translation_version, view_definition ->
        # view_definition_version, xml_field_mapping -> xml_field_mapping_version) are
        # use_alter (created after their target tables, deliberately, so the tables can
        # reference each other) but ARE enforced — null them out before deleting the
        # version rows they point to, or the DELETE below violates the FK.
        session.execute(text("UPDATE mapping_definition SET current_version_id = NULL"))
        session.execute(text("UPDATE enum_translation_table SET current_version_id = NULL"))
        session.execute(text("UPDATE view_definition SET current_version_id = NULL"))
        session.execute(text("UPDATE xml_field_mapping SET current_version_id = NULL"))
        session.execute(text("DELETE FROM run_log_entry"))
        session.execute(text("DELETE FROM mapping_version"))
        session.execute(text("DELETE FROM mapping_definition"))
        session.execute(text("DELETE FROM enum_translation_version"))
        session.execute(text("DELETE FROM enum_translation_table"))
        session.execute(text("DELETE FROM view_deployment_log"))
        session.execute(text("DELETE FROM reconciliation_run"))
        session.execute(text("DELETE FROM view_definition_version"))
        session.execute(text("DELETE FROM view_definition"))
        session.execute(text("DELETE FROM xml_field_mapping_version"))
        session.execute(text("DELETE FROM xml_field_mapping"))
        session.execute(text("DELETE FROM legacy_shape_capture"))
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


@pytest.fixture
def sample_legacy_shape(db_session, sample_connection) -> LegacyShapeCapture:
    """A `legacy_shape_capture` row seeded directly (no live MS SQL Server needed) so
    view-definition validation/versioning tests can run against a known column shape
    matching backend/docker/mssql-init/seed.sql's `dbo.legacy_loan_application`.
    """
    capture = LegacyShapeCapture(
        id=uuid.uuid4(),
        name=f"legacy-loan-application-{uuid.uuid4().hex[:8]}",
        connection_id=sample_connection.id,
        table_name="dbo.legacy_loan_application",
        columns=[
            {"name": "application_id", "type": "INTEGER", "nullable": False},
            {"name": "applicant_first_name", "type": "VARCHAR(100)", "nullable": False},
            {"name": "collateral_value_cents", "type": "BIGINT", "nullable": True},
            {"name": "underwriting_decision", "type": "VARCHAR(50)", "nullable": False},
        ],
    )
    db_session.add(capture)
    db_session.commit()
    db_session.refresh(capture)
    return capture
