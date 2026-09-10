"""Contract tests (T012/T013): `POST /view-definitions` rejects incomplete
`column_mappings` (FR-004) and unreachable `join_graph` tables (FR-002), and rejects a
`name` that collides with the legacy shape's own `table_name` (research.md §5). Also
covers the version-history contract (T031-adjacent: `generated_sql` is retrievable per
version). Fully runnable without a live MS SQL Server — view-definition creation never
opens an external database connection; only preview/deploy do.
"""

import uuid

from tests.conftest import requires_postgres

VALID_JOIN_GRAPH = [
    {
        "left_table": "dbo.loan_application",
        "left_column": "application_id",
        "right_table": "dbo.loan_applicant",
        "right_column": "application_id",
        "join_type": "inner",
    },
    {
        "left_table": "dbo.loan_application",
        "left_column": "application_id",
        "right_table": "dbo.loan_collateral",
        "right_column": "application_id",
        "join_type": "left",
    },
    {
        "left_table": "dbo.loan_application",
        "left_column": "application_id",
        "right_table": "dbo.loan_underwriting",
        "right_column": "application_id",
        "join_type": "inner",
    },
]

VALID_COLUMN_MAPPINGS = [
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
        "source_table": "dbo.loan_collateral",
        "source_column_or_expression": "value_cents",
    },
    {
        "legacy_column": "underwriting_decision",
        "source_table": "dbo.loan_underwriting",
        "source_column_or_expression": "decision",
    },
]


@requires_postgres
def test_create_view_definition_creates_definition_and_first_version(
    client, sample_connection, sample_legacy_shape
):
    response = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"compat-loan-application-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": VALID_JOIN_GRAPH,
            "column_mappings": VALID_COLUMN_MAPPINGS,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["current_version_id"] is not None

    versions = client.get(f"/api/v1/view-definitions/{body['id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert "CREATE OR ALTER VIEW" in versions[0]["generated_sql"]
    assert versions[0]["generated_sql"].index("[application_id]") < versions[0][
        "generated_sql"
    ].index("[underwriting_decision]")


@requires_postgres
def test_create_view_definition_rejects_incomplete_column_mappings(
    client, sample_connection, sample_legacy_shape
):
    incomplete_mappings = VALID_COLUMN_MAPPINGS[:-1]  # drop underwriting_decision
    response = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"incomplete-mapping-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": VALID_JOIN_GRAPH,
            "column_mappings": incomplete_mappings,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "mapping_invalid"
    assert "underwriting_decision" in body["error"]["message"]


@requires_postgres
def test_create_view_definition_rejects_orphan_table_in_join_graph(
    client, sample_connection, sample_legacy_shape
):
    # loan_underwriting is referenced by a column mapping but never joined in —
    # an orphan table per FR-002.
    orphan_join_graph = [
        edge for edge in VALID_JOIN_GRAPH if edge["right_table"] != "dbo.loan_underwriting"
    ]
    response = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"orphan-join-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": orphan_join_graph,
            "column_mappings": VALID_COLUMN_MAPPINGS,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "mapping_invalid"
    assert "loan_underwriting" in body["error"]["message"]


@requires_postgres
def test_create_view_definition_rejects_name_matching_legacy_table_name(
    client, sample_connection, sample_legacy_shape
):
    response = client.post(
        "/api/v1/view-definitions",
        json={
            "name": sample_legacy_shape.table_name,
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": VALID_JOIN_GRAPH,
            "column_mappings": VALID_COLUMN_MAPPINGS,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "name_collision"


@requires_postgres
def test_new_version_does_not_mutate_prior_version(client, sample_connection, sample_legacy_shape):
    create = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"versioned-view-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": VALID_JOIN_GRAPH,
            "column_mappings": VALID_COLUMN_MAPPINGS,
        },
    ).json()

    changed_mappings = [dict(m) for m in VALID_COLUMN_MAPPINGS]
    changed_mappings[1]["source_column_or_expression"] = "last_name"  # was first_name

    updated = client.post(
        f"/api/v1/view-definitions/{create['id']}/versions",
        json={"join_graph": VALID_JOIN_GRAPH, "column_mappings": changed_mappings},
    )
    assert updated.status_code == 201
    assert updated.json()["version_number"] == 2

    versions = client.get(f"/api/v1/view-definitions/{create['id']}/versions").json()
    assert len(versions) == 2
    v1 = next(v for v in versions if v["version_number"] == 1)
    v2 = next(v for v in versions if v["version_number"] == 2)
    assert "loan_applicant.first_name AS [applicant_first_name]" in v1["generated_sql"]
    assert "loan_applicant.last_name AS [applicant_first_name]" in v2["generated_sql"]
