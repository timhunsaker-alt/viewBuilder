"""Integration test (T017): full capture -> define -> preview -> deploy round trip
against the seeded MS SQL Server fixture (backend/docker/mssql-init/seed.sql's
dbo.legacy_loan_application + its 5-table normalized replacement). Asserts the
deployed view's introspected columns exactly match the legacy shape, in order
(FR-006/SC-002). Skips cleanly when no live MS SQL Server / ODBC Driver 18 is
reachable in this sandbox, matching tests/integration/test_execute_run.py's pattern.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine, get_columns
from src.services.legacy_shape_service import LegacyShapeService
from src.services.view_definition_service import ViewDefinitionService
from src.services.view_deployment_service import deploy_view, preview_view
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


def _full_column_mappings() -> list[dict]:
    # Mirrors dbo.legacy_loan_application's exact column order in seed.sql.
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
def test_capture_define_preview_deploy_round_trip(db_session, sample_connection):
    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    # 1. Capture the old table's shape (FR-001).
    shape = LegacyShapeService(db_session).capture(
        name=f"legacy-loan-application-{uuid.uuid4().hex[:8]}",
        connection_id=sample_connection.id,
        table_name="dbo.legacy_loan_application",
    )
    legacy_columns = [c["name"] for c in shape.columns]

    # 2. Define the view (join graph + column mappings).
    view_name = f"dbo.compat_loan_application_{uuid.uuid4().hex[:8]}"
    definition = ViewDefinitionService(db_session).create_view_definition(
        name=view_name,
        legacy_shape_capture_id=shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=_full_column_mappings(),
    )

    # 3. Preview: zero DDL, sample rows returned.
    preview_log = preview_view(db_session, view_definition_id=definition.id)
    assert preview_log.mode == "preview"
    assert preview_log.outcome == "completed"
    with build_engine(sample_connection).connect() as probe:
        exists = probe.execute(text("SELECT OBJECT_ID(:name, 'V')"), {"name": view_name}).scalar()
    assert exists is None, "preview must never create the view (read-only preview policy)"

    # 4. Deploy: real CREATE OR ALTER VIEW; introspected shape must match exactly.
    deploy_log = deploy_view(db_session, view_definition_id=definition.id)
    assert deploy_log.mode == "deploy"
    assert deploy_log.outcome == "completed"

    deployed_columns = [c.name for c in get_columns(sample_connection, view_name)]
    assert deployed_columns == legacy_columns
