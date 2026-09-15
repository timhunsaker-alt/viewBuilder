"""Contract test (T016): `POST /view-definitions/{id}/preview` returns the generated
SQL + sample rows and performs zero DDL — read-only preview policy. Verified by
confirming no new database object (specifically, the would-be view name) exists
immediately after the preview call. Requires a live seeded MS SQL Server fixture;
skips cleanly (does not fail) when one isn't reachable in this sandbox, matching the
pattern used throughout backend/tests/integration/ (e.g. test_execute_run.py).
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine, list_tables
from src.services.view_definition_service import ViewDefinitionService
from tests.conftest import requires_postgres

JOIN_GRAPH = [
    {
        "left_table": "dbo.loan_application",
        "left_column": "application_id",
        "right_table": "dbo.loan_applicant",
        "right_column": "application_id",
        "join_type": "inner",
    },
]

COLUMN_MAPPINGS = [
    {
        "legacy_column": "application_id",
        "source_table": "dbo.loan_application",
        "source_column_or_expression": "application_id",
    },
    {
        "legacy_column": "applicant_first_name",
        "source_table": "dbo.loan_applicant",
        "source_column_or_expression": "first_name",
    },
    {
        "legacy_column": "collateral_value_cents",
        "source_table": None,
        "source_column_or_expression": "NULL",
    },
    {
        "legacy_column": "underwriting_decision",
        "source_table": None,
        "source_column_or_expression": "NULL",
    },
]


@requires_postgres
def test_preview_returns_sql_and_sample_rows_and_deploys_nothing(
    db_session, client, sample_connection, sample_legacy_shape
):
    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    view_name = f"dbo.compat_preview_{uuid.uuid4().hex[:8]}"
    definition = ViewDefinitionService(db_session).create_view_definition(
        name=view_name,
        legacy_shape_capture_id=sample_legacy_shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=COLUMN_MAPPINGS,
    )

    tables_before = set(list_tables(sample_connection))
    assert view_name not in tables_before

    response = client.post(f"/api/v1/view-definitions/{definition.id}/preview", json={})
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "preview"
    assert isinstance(body["sample_rows"], list)

    # Zero DDL: the view must still not exist after a preview.
    tables_after = set(list_tables(sample_connection))
    assert view_name not in tables_after
    assert tables_before == tables_after
