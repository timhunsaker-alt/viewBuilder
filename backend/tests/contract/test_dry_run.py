"""Contract test for POST /mappings/{id}/dry-run.

The "mapping not found" case and the "connection unreachable" clean-error case are both
fully verifiable without a live MS SQL Server. The full-success path additionally
requires a reachable seeded mssql fixture and is skipped cleanly otherwise, matching
the pattern used by tests/contract/test_connections_schema.py.
"""

import uuid

from src.services.mapping_service import MappingService
from tests.conftest import requires_postgres


@requires_postgres
def test_dry_run_for_unknown_mapping_returns_404(client):
    response = client.post(f"/api/v1/mappings/{uuid.uuid4()}/dry-run", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@requires_postgres
def test_dry_run_never_writes_and_reports_cleanly_when_connection_unreachable(
    client, db_session, sample_connection
):
    mapping = MappingService(db_session).create_mapping(
        name=f"dry-run-contract-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        target_connection_id=sample_connection.id,
        target_table="dbo.target_account",
        column_links=[{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
        row_identity_column="account_id",
    )

    response = client.post(f"/api/v1/mappings/{mapping.id}/dry-run", json={})

    assert response.status_code in (201, 503)
    if response.status_code == 503:
        assert response.json()["error"]["code"] == "connection_unreachable"
    else:
        body = response.json()
        assert body["mode"] == "dry_run"
        # read-only preview policy / data-model.md: dry-run always persists 0 actual
        # writes, regardless of how many rows would have been written.
        assert body["target_rows_written"] == 0
        assert body["retirement_records_written"] == 0

    # Whichever branch executed, no run should have silently succeeded with corrupted
    # counts: fetch it back via GET /runs/{id} if one was created.
    runs = client.get("/api/v1/runs", params={"mapping_definition_id": str(mapping.id)}).json()
    for run in runs:
        assert run["target_rows_written"] == 0
