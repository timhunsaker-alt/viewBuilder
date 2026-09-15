"""append-only retirement policy (NON-NEGOTIABLE): retirement must never mutate the source
row — only ever insert a new record into the retirement-audit table. These tests use an
in-memory SQLite database purely as a lightweight, disposable relational engine to
exercise `retirement_writer.run_retirement`'s own SQL-issuing behavior (INSERT-only
against the audit table, read-only against the source table, and dedup-before-insert) in
isolation. Real MS SQL Server dialect behavior is exercised separately by the (skips
cleanly when unavailable) integration test in tests/integration/test_retirement_execute.py
— research.md explains why SQLite is not used as a stand-in for that.
"""

import uuid

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from src.services.retirement_writer import run_retirement


def _build_fixture_engines():
    """Two separate SQLite engines stand in for "source database" and "target
    database" so a cross-connection dedup check is exercised the same way it would be
    against two real, distinct SQL Server connections.
    """
    source_engine = create_engine("sqlite:///:memory:")
    target_engine = create_engine("sqlite:///:memory:")

    source_metadata = MetaData()
    legacy_account = Table(
        "legacy_account",
        source_metadata,
        Column("account_id", Integer, primary_key=True),
        Column("status_code", Integer),
        Column("reason_code", String),
    )
    source_metadata.create_all(source_engine)

    target_metadata = MetaData()
    retirement_audit = Table(
        "retirement_audit",
        target_metadata,
        Column("audit_id", Integer, primary_key=True, autoincrement=True),
        Column("row_identity", String),
        Column("retirement_reason", String),
        Column("retired_at", String),
        Column("mapping_version", String),
    )
    target_metadata.create_all(target_engine)

    with source_engine.begin() as conn:
        conn.execute(
            legacy_account.insert(),
            [
                {"account_id": 101, "status_code": 1, "reason_code": None},
                {"account_id": 102, "status_code": 1, "reason_code": None},
                {"account_id": 103, "status_code": 3, "reason_code": "3"},
            ],
        )

    return source_engine, target_engine, legacy_account, retirement_audit


AUDIT_BINDING = {
    "audit_table": "retirement_audit",
    "row_identity_target_column": "row_identity",
    "reason_target_column": "retirement_reason",
    "timestamp_target_column": "retired_at",
    "mapping_version_target_column": "mapping_version",
}


def test_retirement_never_mutates_the_source_row():
    source_engine, target_engine, legacy_account, _audit_tbl = _build_fixture_engines()

    with source_engine.connect() as source_conn:
        before = list(source_conn.execute(select(legacy_account)).all())

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        run_retirement(
            source_conn=source_conn,
            target_conn=target_conn,
            source_table="legacy_account",
            row_identity_column="account_id",
            status_column="status_code",
            retired_value_codes=["3"],
            reason_column="reason_code",
            reason_translation_entries={"3": "Inactivity"},
            audit_binding=AUDIT_BINDING,
            mapping_version_id=uuid.uuid4(),
        )

    with source_engine.connect() as source_conn:
        after = list(source_conn.execute(select(legacy_account)).all())

    assert before == after, (
        "the source table must be byte-for-byte unchanged after a retirement run "
        "(append-only retirement policy)"
    )


def test_retirement_writes_one_audit_record_per_retired_row():
    source_engine, target_engine, _src_tbl, retirement_audit = _build_fixture_engines()
    mapping_version_id = uuid.uuid4()

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        result = run_retirement(
            source_conn=source_conn,
            target_conn=target_conn,
            source_table="legacy_account",
            row_identity_column="account_id",
            status_column="status_code",
            retired_value_codes=["3"],
            reason_column="reason_code",
            reason_translation_entries={"3": "Inactivity"},
            audit_binding=AUDIT_BINDING,
            mapping_version_id=mapping_version_id,
        )

    assert result.rows_considered == 1
    assert result.audit_records_written == 1
    assert result.duplicates_skipped == 0

    with target_engine.connect() as target_conn:
        rows = list(target_conn.execute(select(retirement_audit)).all())
    assert len(rows) == 1
    row = rows[0]._mapping
    assert row["row_identity"] == "103"
    assert row["retirement_reason"] == "Inactivity"
    assert row["mapping_version"] == str(mapping_version_id)
    assert row["retired_at"] is not None


def test_reason_code_with_no_translation_entry_is_skipped_not_defaulted():
    source_engine, target_engine, _src_tbl, retirement_audit = _build_fixture_engines()

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        result = run_retirement(
            source_conn=source_conn,
            target_conn=target_conn,
            source_table="legacy_account",
            row_identity_column="account_id",
            status_column="status_code",
            retired_value_codes=["3"],
            reason_column="reason_code",
            reason_translation_entries={},  # no entry for code "3"
            audit_binding=AUDIT_BINDING,
            mapping_version_id=uuid.uuid4(),
        )

    assert result.audit_records_written == 0
    assert result.untranslatable_skipped == 1

    with target_engine.connect() as target_conn:
        rows = list(target_conn.execute(select(retirement_audit)).all())
    assert rows == [], "an untranslatable reason must never be written as a default/blank value"


def test_rerunning_over_an_already_retired_row_does_not_duplicate():
    source_engine, target_engine, _src_tbl, retirement_audit = _build_fixture_engines()
    mapping_version_id = uuid.uuid4()
    kwargs = {
        "source_table": "legacy_account",
        "row_identity_column": "account_id",
        "status_column": "status_code",
        "retired_value_codes": ["3"],
        "reason_column": "reason_code",
        "reason_translation_entries": {"3": "Inactivity"},
        "audit_binding": AUDIT_BINDING,
        "mapping_version_id": mapping_version_id,
    }

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        first = run_retirement(source_conn=source_conn, target_conn=target_conn, **kwargs)
    assert first.audit_records_written == 1

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        second = run_retirement(source_conn=source_conn, target_conn=target_conn, **kwargs)

    assert second.audit_records_written == 0
    assert second.duplicates_skipped == 1

    with target_engine.connect() as target_conn:
        rows = list(target_conn.execute(select(retirement_audit)).all())
    assert len(rows) == 1, "re-running over an already-retired row must not duplicate (FR-011)"


def test_dry_run_reports_counts_without_writing_anything():
    source_engine, target_engine, _src_tbl, retirement_audit = _build_fixture_engines()

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        result = run_retirement(
            source_conn=source_conn,
            target_conn=target_conn,
            source_table="legacy_account",
            row_identity_column="account_id",
            status_column="status_code",
            retired_value_codes=["3"],
            reason_column="reason_code",
            reason_translation_entries={"3": "Inactivity"},
            audit_binding=AUDIT_BINDING,
            mapping_version_id=uuid.uuid4(),
            dry_run=True,
        )

    assert result.audit_records_written == 1
    with target_engine.connect() as target_conn:
        rows = list(target_conn.execute(select(retirement_audit)).all())
    assert rows == [], "dry_run must never write to the audit table"
