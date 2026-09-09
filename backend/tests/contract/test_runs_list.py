"""Contract test for GET /runs and GET /runs/{id} filtering (FR-014).

Fully testable against the metadata-store Postgres alone: it inserts run_log_entry rows
directly (bypassing the mssql-dependent orchestrator) since this endpoint only needs to
prove list/filter/get behavior over already-persisted rows.
"""

import uuid
from datetime import UTC, datetime

from src.models.run_log import RunLogEntry
from src.services.mapping_service import MappingService
from tests.conftest import requires_postgres


def _insert_run_log(db_session, *, mapping_version_id, mode) -> RunLogEntry:
    run = RunLogEntry(
        id=uuid.uuid4(),
        mapping_version_id=mapping_version_id,
        mode=mode,
        operator="test-operator",
        completed_at=datetime.now(UTC),
        outcome="completed",
        source_rows_read=3,
        target_rows_written=3 if mode == "execute" else 0,
        retirement_records_written=0,
        untranslatable_rows_flagged=0,
        sample_rows=[],
        production_confirmed=False,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


@requires_postgres
def test_list_and_get_runs_filtered_by_mapping_and_mode(client, db_session, sample_connection):
    mapping_a = MappingService(db_session).create_mapping(
        name=f"runs-list-a-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        target_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        target_table="dbo.target_account",
        column_links=[{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
        row_identity_column="account_id",
    )
    mapping_b = MappingService(db_session).create_mapping(
        name=f"runs-list-b-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        target_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        target_table="dbo.target_account",
        column_links=[{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
        row_identity_column="account_id",
    )

    dry_run_a = _insert_run_log(
        db_session, mapping_version_id=mapping_a.current_version_id, mode="dry_run"
    )
    execute_a = _insert_run_log(
        db_session, mapping_version_id=mapping_a.current_version_id, mode="execute"
    )
    _insert_run_log(db_session, mapping_version_id=mapping_b.current_version_id, mode="dry_run")

    response = client.get("/api/v1/runs", params={"mapping_definition_id": str(mapping_a.id)})
    assert response.status_code == 200
    ids = {run["id"] for run in response.json()}
    assert ids == {str(dry_run_a.id), str(execute_a.id)}

    response = client.get(
        "/api/v1/runs", params={"mapping_definition_id": str(mapping_a.id), "mode": "execute"}
    )
    assert response.status_code == 200
    ids = {run["id"] for run in response.json()}
    assert ids == {str(execute_a.id)}

    response = client.get(f"/api/v1/runs/{execute_a.id}")
    assert response.status_code == 200
    assert response.json()["mode"] == "execute"

    response = client.get(f"/api/v1/runs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
