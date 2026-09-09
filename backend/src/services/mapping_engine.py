"""Applies a mapping version's column links to a source row, including enum
translation (FR-007/FR-008).

Constitution Principle III (NON-NEGOTIABLE): a source enum code with no matching entry
in its attached translation version is never guessed, defaulted, or dropped silently.
This module reports it as an "untranslatable column" for the caller to count/flag
(dry-run preview) or skip (execution) — it never writes a placeholder value for it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models.enum_translation import EnumTranslationVersion


@dataclass
class RowTranslationResult:
    target_row: dict = field(default_factory=dict)
    untranslatable_columns: list[str] = field(default_factory=list)

    @property
    def fully_translatable(self) -> bool:
        return not self.untranslatable_columns


def load_translation_entries(db: Session, column_links: list[dict]) -> dict[str, dict[str, str]]:
    """Preload {version_id: {code: translated_value}} for every enum-translation
    version referenced by column_links, so a row-by-row translation loop does not
    re-query the metadata store per row.
    """
    version_ids = {
        link["enumTranslationVersionId"]
        for link in column_links
        if link.get("enumTranslationVersionId")
    }
    entries_by_version: dict[str, dict[str, str]] = {}
    for version_id in version_ids:
        version = db.get(EnumTranslationVersion, uuid.UUID(str(version_id)))
        if version is None:
            continue
        entries_by_version[str(version_id)] = {
            str(entry["code"]): entry["translated_value"] for entry in version.entries
        }
    return entries_by_version


def translate_row(
    source_row: dict,
    column_links: list[dict],
    translation_entries: dict[str, dict[str, str]],
) -> RowTranslationResult:
    """Apply one mapping version's column_links to one source row.

    For a plain (non-enum) link, the source value is copied through as-is. For an
    enum-coded link, the source value is looked up in its attached translation
    version's entries; a code with no entry is recorded in `untranslatable_columns`
    and is NOT written to `target_row` — callers must not substitute a default.
    """
    result = RowTranslationResult()
    for link in column_links:
        source_column = link["sourceColumn"]
        target_column = link["targetColumn"]
        raw_value = source_row.get(source_column)
        translation_version_id = link.get("enumTranslationVersionId")

        if translation_version_id is None:
            result.target_row[target_column] = raw_value
            continue

        entries = translation_entries.get(str(translation_version_id), {})
        code = None if raw_value is None else str(raw_value)
        if code is None or code not in entries:
            result.untranslatable_columns.append(source_column)
            continue

        result.target_row[target_column] = entries[code]

    return result
