"""Integration test (US2 story): a mapping with an enum-coded column mapped through an
attached enum-translation table produces translated values and a correct
untranslatable-row count when its rows are run through the mapping engine — the same
engine the dry-run endpoint (US4) will orchestrate over real source rows. Exercises the
real seeded `dbo.legacy_account.status_code` column (1=Active, 2=Suspended, 3=Retired)
against a live MS SQL Server fixture when available, and skips cleanly otherwise.
"""

import uuid

import pytest

from src.connectors.mssql import build_engine
from src.services.enum_translation_service import EnumTranslationService
from src.services.mapping_engine import load_translation_entries, translate_row
from src.services.mapping_service import MappingService
from tests.conftest import requires_postgres


@requires_postgres
def test_enum_mapping_translates_and_flags_against_seeded_mssql(db_session, sample_connection):
    translation_table = EnumTranslationService(db_session).create_table(
        name=f"account-status-codes-{uuid.uuid4().hex[:8]}",
        entries=[
            {"code": "1", "translated_value": "Active"},
            {"code": "2", "translated_value": "Suspended"},
            # deliberately no entry for code "3" (Retired), to exercise flagging
        ],
    )

    mapping = MappingService(db_session).create_mapping(
        name=f"account-status-mapping-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        source_table="dbo.legacy_account",
        target_connection_id=sample_connection.id,
        target_table="dbo.target_account",
        column_links=[
            {
                "sourceColumn": "status_code",
                "targetColumn": "status",
                "enumTranslationVersionId": str(translation_table.current_version_id),
            }
        ],
        row_identity_column="account_id",
    )
    version = MappingService(db_session).list_versions(mapping.id)[0]

    try:
        from sqlalchemy import text  # noqa: PLC0415

        engine = build_engine(sample_connection)
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT account_id, status_code FROM dbo.legacy_account ORDER BY account_id"
                    )
                )
                .mappings()
                .all()
            )
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    translation_entries = load_translation_entries(db_session, version.column_links)

    translated_count = 0
    flagged_count = 0
    sample_rows = []
    for row in rows:
        result = translate_row(dict(row), version.column_links, translation_entries)
        sample_rows.append(result)
        if result.fully_translatable:
            translated_count += 1
        else:
            flagged_count += 1

    # Seeded data: account 101 (status 1=Active), 102 (status 1=Active), 103 (status
    # 3=Retired, deliberately untranslated by this test's translation table).
    assert translated_count == 2
    assert flagged_count == 1
    assert any(r.target_row.get("status") == "Active" for r in sample_rows)
    assert any(not r.fully_translatable for r in sample_rows)
