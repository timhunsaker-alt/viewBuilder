"""Integration test (US4 story): dry-running a mapping against the seeded MS SQL Server
fixture reports correct counts/sample rows and writes zero rows to the target table
(US4 AC1-AC3). Skips cleanly when no live MS SQL Server / ODBC Driver 18 is reachable.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine
from src.services.mapping_service import MappingService
from src.services.run_orchestrator import run_mapping
from tests.conftest import requires_postgres


@requires_postgres
def test_dry_run_against_seeded_mssql_writes_nothing(db_session, sample_connection):
    mapping = MappingService(db_session).create_mapping(
        name=f"dry-run-integration-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        target_connection_id=sample_connection.id,
        target_table="dbo.target_account",
        column_links=[{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
        row_identity_column="account_id",
    )

    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            before_count = probe.execute(
                text("SELECT COUNT(*) FROM dbo.target_account")
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    run_log = run_mapping(
        db_session, mapping_definition_id=mapping.id, mode="dry_run", operator="test-operator"
    )

    assert run_log.mode == "dry_run"
    assert run_log.source_rows_read == 3  # seeded dbo.legacy_account has 3 rows
    assert run_log.target_rows_written == 0
    assert len(run_log.sample_rows) > 0

    with engine.connect() as probe:
        after_count = probe.execute(text("SELECT COUNT(*) FROM dbo.target_account")).scalar_one()

    assert after_count == before_count, "dry-run must never write to the target table"
