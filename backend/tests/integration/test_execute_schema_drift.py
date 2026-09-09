"""Integration test (US5 story, FR-015): if a mapping references a source or target
column that no longer exists, execute must fail with a clear schema-drift error and
zero partial writes — never fail mid-write. Skips cleanly when no live MS SQL Server /
ODBC Driver 18 is reachable in this environment.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine
from src.services.mapping_service import MappingService
from src.services.run_orchestrator import SchemaDriftError, run_mapping
from tests.conftest import requires_postgres


@requires_postgres
def test_execute_blocks_with_no_partial_writes_when_a_mapped_column_is_missing(
    db_session, sample_connection
):
    mapping = MappingService(db_session).create_mapping(
        name=f"schema-drift-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        target_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        # target_account has no such column — simulates schema drift after mapping-save.
        target_table="dbo.target_account",
        column_links=[
            {"sourceColumn": "balance_cents", "targetColumn": "this_column_does_not_exist"}
        ],
        row_identity_column="account_id",
    )

    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
            before_count = probe.execute(
                text("SELECT COUNT(*) FROM dbo.target_account")
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    with pytest.raises(SchemaDriftError):
        run_mapping(
            db_session, mapping_definition_id=mapping.id, mode="execute", operator="test-operator"
        )

    with engine.connect() as probe:
        after_count = probe.execute(text("SELECT COUNT(*) FROM dbo.target_account")).scalar_one()
    assert after_count == before_count, "a blocked execute must leave the target untouched"
