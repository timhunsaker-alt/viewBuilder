"""Unit test (US5, FR-008/AC3): during a real execute, a row with an untranslatable
enum-coded column is never written to the target with a guessed/defaulted value — it is
skipped entirely and counted. Uses two in-memory SQLite engines as disposable "source"
and "target" databases to exercise `run_column_mapping`'s own row-by-row write behavior
in isolation, the same pattern used by tests/unit/test_retirement_writer.py and
justified the same way in research.md (SQLite is not used as an MS SQL Server dialect
stand-in — only as a lightweight engine to prove this module's own SQL-issuing logic).
"""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from src.services.run_orchestrator import run_column_mapping


def _build_fixture():
    source_engine = create_engine("sqlite:///:memory:")
    target_engine = create_engine("sqlite:///:memory:")

    source_metadata = MetaData()
    legacy_account = Table(
        "legacy_account",
        source_metadata,
        Column("account_id", Integer, primary_key=True),
        Column("status_code", Integer),
    )
    source_metadata.create_all(source_engine)

    target_metadata = MetaData()
    target_account = Table(
        "target_account",
        target_metadata,
        Column("account_id", Integer, primary_key=True),
        Column("status", String),
    )
    target_metadata.create_all(target_engine)

    with source_engine.begin() as conn:
        conn.execute(
            legacy_account.insert(),
            [
                {"account_id": 1, "status_code": 1},
                {"account_id": 2, "status_code": 2},
                {"account_id": 3, "status_code": 9},  # no translation entry for 9
            ],
        )

    return source_engine, target_engine, target_account


COLUMN_LINKS = [
    {
        "sourceColumn": "status_code",
        "targetColumn": "status",
        "enumTranslationVersionId": "v1",
    }
]
TRANSLATION_ENTRIES = {"v1": {"1": "Active", "2": "Suspended"}}  # nothing for code 9


def test_untranslatable_row_is_skipped_not_defaulted_on_execute():
    source_engine, target_engine, target_account = _build_fixture()

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        result = run_column_mapping(
            source_conn=source_conn,
            target_conn=target_conn,
            source_table="legacy_account",
            target_table="target_account",
            column_links=COLUMN_LINKS,
            translation_entries=TRANSLATION_ENTRIES,
            dry_run=False,
        )

    assert result.source_rows_read == 3
    assert result.target_rows_written == 2
    assert result.untranslatable_rows_flagged == 1

    with target_engine.connect() as target_conn:
        written = list(target_conn.execute(select(target_account)).all())

    assert len(written) == 2, "the untranslatable row must never be written, not even partially"
    written_statuses = {row.status for row in written}
    assert written_statuses == {"Active", "Suspended"}
    assert None not in written_statuses
    assert "" not in written_statuses


def test_dry_run_writes_nothing_at_all_even_for_translatable_rows():
    source_engine, target_engine, target_account = _build_fixture()

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        result = run_column_mapping(
            source_conn=source_conn,
            target_conn=target_conn,
            source_table="legacy_account",
            target_table="target_account",
            column_links=COLUMN_LINKS,
            translation_entries=TRANSLATION_ENTRIES,
            dry_run=True,
        )

    assert result.target_rows_written == 2  # "would write" count, internal to this function
    with target_engine.connect() as target_conn:
        written = list(target_conn.execute(select(target_account)).all())
    assert written == [], "dry_run must never write to the target table (Constitution Principle I)"
