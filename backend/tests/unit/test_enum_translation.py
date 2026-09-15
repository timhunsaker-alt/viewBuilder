"""explicit translation policy (NON-NEGOTIABLE): enum translation must never guess,
default, or silently drop an unmapped code. These tests prove that property directly
against the real translation-application code path (mapping_engine.translate_row), not
just against a mock.
"""

import pytest

from src.services.enum_translation_service import (
    EnumTranslationService,
    EnumTranslationValidationError,
)
from src.services.mapping_engine import load_translation_entries, translate_row
from tests.conftest import requires_postgres


@requires_postgres
def test_known_code_translates_to_its_value(db_session):
    table = EnumTranslationService(db_session).create_table(
        name="status-codes-known",
        entries=[
            {"code": "0", "translated_value": "Active"},
            {"code": "1", "translated_value": "Retired"},
        ],
    )
    column_links = [
        {
            "sourceColumn": "status_code",
            "targetColumn": "status",
            "enumTranslationVersionId": str(table.current_version_id),
        }
    ]
    entries = load_translation_entries(db_session, column_links)

    result = translate_row({"status_code": "1"}, column_links, entries)

    assert result.target_row == {"status": "Retired"}
    assert result.untranslatable_columns == []
    assert result.fully_translatable


@requires_postgres
def test_unmapped_code_is_flagged_not_guessed_or_defaulted(db_session):
    table = EnumTranslationService(db_session).create_table(
        name="status-codes-partial",
        entries=[{"code": "0", "translated_value": "Active"}],
    )
    column_links = [
        {
            "sourceColumn": "status_code",
            "targetColumn": "status",
            "enumTranslationVersionId": str(table.current_version_id),
        }
    ]
    entries = load_translation_entries(db_session, column_links)

    # code "9" has no entry in the attached translation version.
    result = translate_row({"status_code": "9"}, column_links, entries)

    assert (
        "status" not in result.target_row
    ), "an untranslatable code must never be written as a guessed/default/blank value"
    assert result.untranslatable_columns == ["status_code"]
    assert not result.fully_translatable


@requires_postgres
def test_null_source_value_is_flagged_not_translated_to_a_default(db_session):
    table = EnumTranslationService(db_session).create_table(
        name="status-codes-null",
        entries=[{"code": "0", "translated_value": "Active"}],
    )
    column_links = [
        {
            "sourceColumn": "status_code",
            "targetColumn": "status",
            "enumTranslationVersionId": str(table.current_version_id),
        }
    ]
    entries = load_translation_entries(db_session, column_links)

    result = translate_row({"status_code": None}, column_links, entries)

    assert "status" not in result.target_row
    assert result.untranslatable_columns == ["status_code"]


@requires_postgres
def test_plain_non_enum_link_passes_value_through_unchanged(db_session):
    column_links = [{"sourceColumn": "full_name", "targetColumn": "display_name"}]
    entries = load_translation_entries(db_session, column_links)

    result = translate_row({"full_name": "Ada Lovelace"}, column_links, entries)

    assert result.target_row == {"display_name": "Ada Lovelace"}
    assert result.fully_translatable


def test_duplicate_code_within_one_version_is_rejected():
    with pytest.raises(EnumTranslationValidationError):
        from src.services.enum_translation_service import _validate_entries  # noqa: PLC0415

        _validate_entries(
            [
                {"code": "1", "translated_value": "A"},
                {"code": "1", "translated_value": "B"},
            ]
        )


def test_entries_missing_translated_value_are_rejected():
    with pytest.raises(EnumTranslationValidationError):
        from src.services.enum_translation_service import _validate_entries  # noqa: PLC0415

        _validate_entries([{"code": "1"}])
