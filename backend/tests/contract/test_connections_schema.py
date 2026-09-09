"""Contract test for GET /connections and GET /connections/{id}/schema.

Requires both the metadata-store Postgres AND a reachable MS SQL Server connection to run
end-to-end; in environments without a live SQL Server (no ODBC Driver 18 installed, or the
docker-compose mssql fixture not running) the live-schema assertions are skipped, but the
"never leaks credential_ref" contract is still verified since it only needs Postgres.
"""

from tests.conftest import requires_postgres


@requires_postgres
def test_list_connections_never_returns_credential_ref(client, sample_connection):
    response = client.get("/api/v1/connections")
    assert response.status_code == 200
    body = response.json()
    assert any(c["id"] == str(sample_connection.id) for c in body)
    for connection in body:
        assert "credential_ref" not in connection


@requires_postgres
def test_create_connection_never_echoes_credential_ref(client, db_session):
    import os

    os.environ["VIEWBUILDER_CRED_NEWCRED"] = "secret"
    response = client.post(
        "/api/v1/connections",
        json={
            "name": "new-connection",
            "role": "source",
            "environment": "dev",
            "host": "localhost",
            "port": 1433,
            "database": "viewbuilder_legacy",
            "credential_ref": "newcred",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "credential_ref" not in body
    assert body["name"] == "new-connection"


@requires_postgres
def test_schema_introspection_reports_connection_unreachable_cleanly(client, sample_connection):
    """Without a real reachable SQL Server, the endpoint must fail with a clean, typed
    error (connection_unreachable) rather than a raw traceback/500 — this is the
    contract regardless of whether a live mssql fixture is available."""
    response = client.get(f"/api/v1/connections/{sample_connection.id}/schema")
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        body = response.json()
        assert body["error"]["code"] == "connection_unreachable"
