"""Contract test (T011): `POST /legacy-shapes` and `GET /legacy-shapes/{id}/drift`.

The "unknown connection" validation-error case is fully verifiable without a live MS
SQL Server. The full capture/drift path additionally requires a reachable seeded mssql
fixture and degrades cleanly (asserts the `connection_unreachable` error shape) when
one isn't available, matching the pattern used by
tests/contract/test_dry_run.py / tests/contract/test_connections_schema.py.
"""

import uuid

from tests.conftest import requires_postgres


@requires_postgres
def test_capture_for_unknown_connection_returns_mapping_invalid(client):
    response = client.post(
        "/api/v1/legacy-shapes",
        json={
            "name": f"unknown-conn-{uuid.uuid4().hex[:8]}",
            "connection_id": str(uuid.uuid4()),
            "table_name": "dbo.legacy_loan_application",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mapping_invalid"


@requires_postgres
def test_capture_and_drift_round_trip_or_reports_unreachable_cleanly(client, sample_connection):
    response = client.post(
        "/api/v1/legacy-shapes",
        json={
            "name": f"legacy-loan-application-{uuid.uuid4().hex[:8]}",
            "connection_id": str(sample_connection.id),
            "table_name": "dbo.legacy_loan_application",
        },
    )

    assert response.status_code in (201, 503)
    if response.status_code == 503:
        assert response.json()["error"]["code"] == "connection_unreachable"
        return

    body = response.json()
    assert body["table_name"] == "dbo.legacy_loan_application"
    assert len(body["columns"]) > 0
    # Columns must be captured in their original left-to-right order (FR-001) —
    # application_id is the first column of dbo.legacy_loan_application in seed.sql.
    assert body["columns"][0]["name"] == "application_id"

    drift = client.get(f"/api/v1/legacy-shapes/{body['id']}/drift")
    assert drift.status_code == 200
    drift_body = drift.json()
    # A freshly-captured shape, re-introspected immediately, must show no drift.
    assert drift_body["drifted"] is False
    assert drift_body["added_columns"] == []
    assert drift_body["removed_columns"] == []
    assert drift_body["retyped_columns"] == []


@requires_postgres
def test_drift_for_unknown_capture_returns_404(client):
    response = client.get(f"/api/v1/legacy-shapes/{uuid.uuid4()}/drift")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
