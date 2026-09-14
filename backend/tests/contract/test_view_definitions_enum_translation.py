"""Contract tests: a column_mappings entry can reference an enum_translation_version
(mirrors 001-sql-view-builder's enumTranslationVersionId on mapping column_links) —
`POST /view-definitions` bakes the translation into the generated view SQL as a `CASE`
(ddl_generator.py), and rejects a reference to an enum translation version that does
not exist (mirrors mapping_service's FR-005 validation).
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


def _column_mappings(enum_translation_version_id: str | None) -> list[dict]:
    return [
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
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "collateral_value_cents",
        },
        {
            "legacy_column": "underwriting_decision",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "decision_code",
            "enum_translation_version_id": enum_translation_version_id,
        },
    ]


@requires_postgres
def test_enum_coded_column_mapping_bakes_a_case_into_the_generated_sql(
    client, sample_connection, sample_legacy_shape
):
    enum_table = client.post(
        "/api/v1/enum-translations",
        json={
            "name": f"decision-codes-{uuid.uuid4().hex[:8]}",
            "entries": [
                {"code": "A", "translated_value": "Approved"},
                {"code": "D", "translated_value": "Denied"},
            ],
        },
    ).json()

    response = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"compat-enum-view-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": JOIN_GRAPH,
            "column_mappings": _column_mappings(enum_table["current_version_id"]),
        },
    )
    assert response.status_code == 201
    body = response.json()

    versions = client.get(f"/api/v1/view-definitions/{body['id']}/versions").json()
    generated_sql = versions[0]["generated_sql"]
    assert "CASE CAST(loan_application.decision_code AS NVARCHAR(4000))" in generated_sql
    assert "WHEN N'A' THEN N'Approved'" in generated_sql
    assert "WHEN N'D' THEN N'Denied'" in generated_sql
    assert "ELSE NULL END" in generated_sql


@requires_postgres
def test_create_view_definition_rejects_a_nonexistent_enum_translation_version(
    client, sample_connection, sample_legacy_shape
):
    response = client.post(
        "/api/v1/view-definitions",
        json={
            "name": f"compat-bad-enum-{uuid.uuid4().hex[:8]}",
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "target_connection_id": str(sample_connection.id),
            "join_graph": JOIN_GRAPH,
            "column_mappings": _column_mappings(str(uuid.uuid4())),
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "mapping_invalid"
    assert "does not exist" in body["error"]["message"]
