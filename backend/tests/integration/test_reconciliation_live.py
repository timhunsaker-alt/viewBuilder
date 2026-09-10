"""Integration test (T039): reconcile a cleanly deployed view against the seeded
mssql fixture (zero discrepancies), then redeploy a deliberately-wrong column
mapping and reconcile again (discrepancy correctly flagged, and nothing else).
Skips cleanly when no live MS SQL Server / ODBC Driver 18 is reachable in this
sandbox, matching tests/integration/test_view_deploy_roundtrip.py's pattern.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine
from src.services.legacy_shape_service import LegacyShapeService
from src.services.view_definition_service import ViewDefinitionService
from src.services.view_deployment_service import deploy_view
from tests.conftest import requires_postgres

JOIN_GRAPH = [
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
    {
        "left_table": "dbo.loan_application",
        "left_column": "application_id",
        "right_table": "dbo.loan_document_ref",
        "right_column": "application_id",
        "join_type": "inner",
    },
]


def _correct_column_mappings() -> list[dict]:
    table_by_column = {
        "application_id": ("dbo.loan_application", "application_id"),
        "applicant_first_name": ("dbo.loan_applicant", "first_name"),
        "applicant_last_name": ("dbo.loan_applicant", "last_name"),
        "applicant_ssn_last4": ("dbo.loan_applicant", "ssn_last4"),
        "applicant_email": ("dbo.loan_applicant", "email"),
        "applicant_phone": ("dbo.loan_applicant", "phone"),
        "loan_amount_cents": ("dbo.loan_application", "loan_amount_cents"),
        "loan_purpose": ("dbo.loan_application", "loan_purpose"),
        "interest_rate_bps": ("dbo.loan_application", "interest_rate_bps"),
        "term_months": ("dbo.loan_application", "term_months"),
        "collateral_description": ("dbo.loan_collateral", "description"),
        "collateral_value_cents": ("dbo.loan_collateral", "value_cents"),
        "collateral_type": ("dbo.loan_collateral", "collateral_type"),
        "underwriter_name": ("dbo.loan_underwriting", "underwriter_name"),
        "underwriting_decision": ("dbo.loan_underwriting", "decision"),
        "underwriting_score": ("dbo.loan_underwriting", "score"),
        "document_ref_number": ("dbo.loan_document_ref", "document_ref_number"),
        "application_date": ("dbo.loan_application", "application_date"),
        "status": ("dbo.loan_application", "status"),
    }
    return [
        {
            "legacy_column": legacy_column,
            "source_table": source_table,
            "source_column_or_expression": source_column,
        }
        for legacy_column, (source_table, source_column) in table_by_column.items()
    ]


@requires_postgres
def test_reconcile_clean_deploy_then_flags_a_deliberately_wrong_mapping(
    db_session, client, sample_connection
):
    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    shape = LegacyShapeService(db_session).capture(
        name=f"legacy-loan-application-{uuid.uuid4().hex[:8]}",
        connection_id=sample_connection.id,
        table_name="dbo.legacy_loan_application",
    )

    view_name = f"dbo.compat_reconcile_{uuid.uuid4().hex[:8]}"
    service = ViewDefinitionService(db_session)
    definition = service.create_view_definition(
        name=view_name,
        legacy_shape_capture_id=shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=_correct_column_mappings(),
    )
    deploy_view(db_session, view_definition_id=definition.id)

    clean_response = client.post(
        f"/api/v1/view-definitions/{definition.id}/reconcile",
        json={"identity_column": "application_id"},
    )
    assert clean_response.status_code == 201
    clean_body = clean_response.json()
    assert clean_body["rows_old_only"] == 0
    assert clean_body["rows_view_only"] == 0
    assert clean_body["rows_with_column_mismatch"] == 0
    assert clean_body["row_inflation_flagged"] is False
    assert clean_body["rows_matched"] == 10  # all 10 seeded loan applications
    assert clean_body["discrepancy_detail"] == []

    # Deliberately wrong mapping: loan_purpose is now sourced from the wrong column.
    broken_mappings = [dict(m) for m in _correct_column_mappings()]
    for mapping in broken_mappings:
        if mapping["legacy_column"] == "loan_purpose":
            mapping["source_column_or_expression"] = "status"  # wrong column, on purpose

    broken_version = service.save_new_version(
        view_definition_id=definition.id,
        join_graph=JOIN_GRAPH,
        column_mappings=broken_mappings,
    )
    deploy_view(
        db_session, view_definition_id=definition.id, view_definition_version_id=broken_version.id
    )

    broken_response = client.post(
        f"/api/v1/view-definitions/{definition.id}/reconcile",
        json={
            "view_definition_version_id": str(broken_version.id),
            "identity_column": "application_id",
        },
    )
    assert broken_response.status_code == 201
    broken_body = broken_response.json()
    assert broken_body["rows_old_only"] == 0
    assert broken_body["rows_view_only"] == 0
    assert broken_body["row_inflation_flagged"] is False
    # Every one of the 10 rows now has a loan_purpose mismatch, and nothing else does.
    assert broken_body["rows_with_column_mismatch"] == 10
    assert broken_body["rows_matched"] == 0
    mismatched_columns = {d["column"] for d in broken_body["discrepancy_detail"]}
    assert mismatched_columns == {"loan_purpose"}
