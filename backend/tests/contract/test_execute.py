"""Contract test for POST /mappings/{id}/execute.

The production-confirmation gate (FR-016) is fully verifiable without any live SQL
Server connection: it must block *before* ever attempting to connect. The
connection-unreachable clean-error path is also verifiable. Full-success execution
additionally requires a reachable seeded mssql fixture and is covered by
tests/integration/test_execute_run.py, skipping cleanly when unavailable.
"""

import uuid

from src.services.mapping_service import MappingService
from tests.conftest import requires_postgres


@requires_postgres
def test_execute_for_unknown_mapping_returns_404(client):
    response = client.post(f"/api/v1/mappings/{uuid.uuid4()}/execute", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@requires_postgres
def test_execute_against_production_connection_requires_confirmation(client, db_session):
    import os

    os.environ["VIEWBUILDER_CRED_PRODCRED"] = "unused"
    prod_connection = client.post(
        "/api/v1/connections",
        json={
            "name": f"prod-connection-{uuid.uuid4().hex[:8]}",
            "role": "either",
            "environment": "prod",
            "host": "prod.example.internal",
            "port": 1433,
            "database": "viewbuilder_legacy",
            "credential_ref": "prodcred",
        },
    ).json()

    mapping = MappingService(db_session).create_mapping(
        name=f"prod-mapping-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=uuid.UUID(prod_connection["id"]),
        target_connection_id=uuid.UUID(prod_connection["id"]),
        source_table="dbo.legacy_account",
        target_table="dbo.target_account",
        column_links=[{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
        row_identity_column="account_id",
    )

    # No confirm_production flag at all: must be blocked with NO connection attempt.
    response = client.post(f"/api/v1/mappings/{mapping.id}/execute", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "production_confirmation_required"

    # Explicitly false: still blocked.
    response = client.post(
        f"/api/v1/mappings/{mapping.id}/execute", json={"confirm_production": False}
    )
    assert response.status_code == 409

    # No run_log_entry should exist for this mapping — a blocked execute attempts
    # nothing and logs nothing (FR-016: "no writes attempted").
    runs = client.get("/api/v1/runs", params={"mapping_definition_id": str(mapping.id)}).json()
    assert runs == []


@requires_postgres
def test_execute_reports_cleanly_when_connection_unreachable(client, db_session, sample_connection):
    mapping = MappingService(db_session).create_mapping(
        name=f"execute-contract-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        target_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        target_table="dbo.target_account",
        column_links=[{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
        row_identity_column="account_id",
    )

    response = client.post(f"/api/v1/mappings/{mapping.id}/execute", json={})
    # sample_connection is environment="dev", so no 409 here — either a real run
    # succeeded (201, needs live mssql) or it failed cleanly reaching it (503/422).
    assert response.status_code in (201, 422, 503)
    if response.status_code == 503:
        assert response.json()["error"]["code"] == "connection_unreachable"
