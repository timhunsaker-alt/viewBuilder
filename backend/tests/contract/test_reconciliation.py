"""Contract test (T038): `POST /view-definitions/{id}/reconcile` returns
`not_deployed` for a version with no successful deploy log entry — you can't
reconcile a view that was only ever previewed (contracts/api.md). Fully runnable
without a live MS SQL Server: creating a view definition never opens an external
database connection, and this test never calls preview/deploy, so it never touches
one either.
"""

import uuid

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
def test_reconcile_rejects_a_version_that_was_never_deployed(
    client, sample_connection, sample_legacy_shape
):
    created = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"never-deployed-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": JOIN_GRAPH,
            "column_mappings": COLUMN_MAPPINGS,
        },
    ).json()

    response = client.post(
        f"/api/v1/view-definitions/{created['id']}/reconcile",
        json={"identity_column": "application_id"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_deployed"


@requires_postgres
def test_reconcile_rejects_unknown_view_definition(client):
    response = client.post(
        f"/api/v1/view-definitions/{uuid.uuid4()}/reconcile",
        json={"identity_column": "application_id"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
