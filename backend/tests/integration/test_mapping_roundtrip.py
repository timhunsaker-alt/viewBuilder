"""Integration test: full save -> reopen round trip against the seeded mssql fixture
(US1 Independent Test). Only the metadata-store (Postgres) side is exercised for the
round trip itself; a real column-link against the live legacy schema is additionally
attempted when MS SQL Server is reachable, and skipped otherwise.
"""

import uuid

import pytest

from src.connectors.mssql import ConnectionUnreachableError, list_tables
from tests.conftest import requires_postgres


@requires_postgres
def test_save_then_reopen_mapping_has_same_links(client, sample_connection):
    created = client.post(
        "/api/v1/mappings",
        json={
            "name": f"roundtrip-{uuid.uuid4().hex[:8]}",
            "kind": "column_mapping",
            "source_connection_id": str(sample_connection.id),
            "source_table": "dbo.legacy_customer",
            "target_connection_id": str(sample_connection.id),
            "target_table": "dbo.target_customer",
            "column_links": [
                {"sourceColumn": "full_name", "targetColumn": "display_name"},
                {"sourceColumn": "email", "targetColumn": "email_address"},
            ],
            "row_identity_column": "customer_id",
        },
    ).json()

    reopened = client.get(f"/api/v1/mappings/{created['id']}").json()
    reopened_versions = client.get(f"/api/v1/mappings/{created['id']}/versions").json()

    assert reopened["name"] == created["name"]
    assert len(reopened_versions) == 1
    assert reopened_versions[0]["column_links"] == [
        {"sourceColumn": "full_name", "targetColumn": "display_name"},
        {"sourceColumn": "email", "targetColumn": "email_address"},
    ]


@requires_postgres
def test_live_mssql_introspection_when_available(db_session, sample_connection):
    """Best-effort: exercises the real connector against the docker-compose mssql
    fixture. Skips cleanly (does not fail the suite) when no live SQL Server / ODBC
    Driver 18 is reachable in this environment."""
    try:
        tables = list_tables(sample_connection)
    except ConnectionUnreachableError:
        pytest.skip("live MS SQL Server fixture not reachable in this environment")
    assert "dbo.legacy_customer" in tables
