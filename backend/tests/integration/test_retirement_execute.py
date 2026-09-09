"""Integration test (US3 story): execute a real retirement mapping against the seeded
MS SQL Server fixture — dbo.legacy_account (status_code=3 means Retired) plus
dbo.legacy_retirement_reason (reason_code) as the source, dbo.retirement_audit as the
target. Asserts the source row is unchanged and a correct audit row exists. Skips
cleanly when no live MS SQL Server / ODBC Driver 18 is reachable in this environment.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine
from src.services.retirement_writer import run_retirement
from tests.conftest import requires_postgres

REASON_TRANSLATIONS = {
    "1": "UserRequested",
    "2": "Fraud",
    "3": "Inactivity",
    "4": "Duplicate",
}

AUDIT_BINDING = {
    "audit_table": "dbo.retirement_audit",
    "row_identity_target_column": "row_identity",
    "reason_target_column": "retirement_reason",
    "timestamp_target_column": "retired_at",
    "mapping_version_target_column": "mapping_version",
}


@requires_postgres
def test_execute_retirement_against_seeded_mssql_leaves_source_unchanged(sample_connection):
    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    mapping_version_id = uuid.uuid4()

    with engine.connect() as conn:
        before = conn.execute(
            text(
                "SELECT account_id, customer_id, status_code, balance_cents "
                "FROM dbo.legacy_account ORDER BY account_id"
            )
        ).all()

        # Clean up any audit row a prior run of this test left behind, so the test is
        # re-runnable — this DELETE targets only the audit table, never the source.
        conn.execute(text("DELETE FROM dbo.retirement_audit WHERE row_identity = '103'"))
        conn.commit()

        result = run_retirement(
            source_conn=conn,
            target_conn=conn,
            source_table="dbo.legacy_retirement_reason",
            row_identity_column="account_id",
            status_column="account_id",  # every row in this legacy table IS a retirement
            retired_value_codes=["103"],
            reason_column="reason_code",
            reason_translation_entries=REASON_TRANSLATIONS,
            audit_binding=AUDIT_BINDING,
            mapping_version_id=mapping_version_id,
        )

        after = conn.execute(
            text(
                "SELECT account_id, customer_id, status_code, balance_cents "
                "FROM dbo.legacy_account ORDER BY account_id"
            )
        ).all()

        audit_rows = conn.execute(
            text(
                "SELECT row_identity, retirement_reason, mapping_version "
                "FROM dbo.retirement_audit WHERE row_identity = '103'"
            )
        ).all()

    assert before == after, "source table must be unchanged after retirement execution"
    assert result.audit_records_written == 1
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == "103"
    assert audit_rows[0][1] == "Inactivity"
    assert audit_rows[0][2] == str(mapping_version_id)
