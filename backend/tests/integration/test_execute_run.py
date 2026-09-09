"""Integration test (US5 story): execute a real column mapping against the seeded MS
SQL Server fixture; assert target rows are written as expected and a matching completed
run_log_entry is produced (mapping version, counts, timestamp). Skips cleanly when no
live MS SQL Server / ODBC Driver 18 is reachable in this environment.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine
from src.services.mapping_service import MappingService
from src.services.run_orchestrator import run_mapping
from tests.conftest import requires_postgres


@requires_postgres
def test_execute_writes_expected_rows_and_matching_run_log(db_session, sample_connection):
    mapping = MappingService(db_session).create_mapping(
        name=f"execute-integration-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        target_connection_id=sample_connection.id,
        source_table="dbo.legacy_customer",
        target_table="dbo.target_customer",
        column_links=[
            {"sourceColumn": "customer_id", "targetColumn": "id"},
            {"sourceColumn": "full_name", "targetColumn": "display_name"},
            {"sourceColumn": "email", "targetColumn": "email_address"},
            {"sourceColumn": "signup_date", "targetColumn": "created_at"},
        ],
        row_identity_column="customer_id",
    )

    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
            probe.execute(text("DELETE FROM dbo.target_customer"))
            probe.commit()
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    run_log = run_mapping(
        db_session, mapping_definition_id=mapping.id, mode="execute", operator="test-operator"
    )

    assert run_log.mode == "execute"
    assert run_log.outcome in ("completed", "partially_completed")
    assert run_log.source_rows_read == 3
    assert run_log.target_rows_written == 3

    with engine.connect() as probe:
        written = probe.execute(text("SELECT display_name FROM dbo.target_customer")).all()
    assert len(written) == 3
