"""XML fallback field lookup (FR-011/FR-012, spec.md User Story 4, research.md §1).

Pushes extraction down as plain T-SQL using SQL Server's native `xml` column
`.value()` method rather than pulling documents into Python: an `EXISTS` check on the
identity and a `.value()` extraction distinguish all three required outcomes (found /
field_missing / document_not_found) in at most two lightweight round trips, without
ever fetching a document's full body. Strictly read-only — every statement issued
here is a `SELECT` (Constitution Principle I); no code path in this module ever
issues UPDATE/DELETE/DROP against the XML store.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from src.connectors.mssql import build_engine
from src.models.connection_config import ConnectionConfig

OUTCOMES = ("found", "field_missing", "document_not_found")

DEFAULT_CAST_TYPE = "NVARCHAR(4000)"


class XmlFieldNotConfiguredError(Exception):
    """FR-011: no `field_paths` entry exists yet for the requested `legacy_column` on
    this mapping's version. Callers map this to contracts/api.md's `mapping_invalid`.
    """


@dataclass
class XmlLookupResult:
    identity: str
    legacy_column: str
    outcome: str
    value: str | None = None


def find_field_path(field_paths: list[dict], legacy_column: str) -> dict:
    """US4 AC4: field_paths is not required to cover every legacy column at once —
    only the ones under investigation. Raise loudly (never guess/default) when the
    requested column has no entry, per Constitution Principle III's spirit."""
    for entry in field_paths:
        if entry.get("legacy_column") == legacy_column:
            return entry
    raise XmlFieldNotConfiguredError(
        f"no field_paths entry configured for legacy_column '{legacy_column}' (FR-011); "
        "add one before running a lookup for it"
    )


def lookup_xml_field(
    connection: ConnectionConfig,
    *,
    xml_table_name: str,
    xml_identity_column: str,
    xml_payload_column: str,
    identity: str,
    legacy_column: str,
    field_paths: list[dict],
) -> XmlLookupResult:
    """FR-012: distinguishes `document_not_found` (no row for `identity` at all),
    `field_missing` (the document exists but the configured XPath resolves to NULL),
    and `found` (a value was extracted) — never a blank/ambiguous result.
    """
    field_path = find_field_path(field_paths, legacy_column)
    xpath = field_path["xpath"]
    cast_type = field_path.get("cast_type") or DEFAULT_CAST_TYPE
    # SQL Server's .value() XQuery argument must be a string literal, not a bind
    # parameter — escape single quotes defensively since it's still interpolated text.
    safe_xpath = xpath.replace("'", "''")
    safe_cast_type = cast_type.replace("'", "''")

    engine = build_engine(connection)
    with engine.connect() as conn:
        document_exists = conn.execute(
            text(
                f"SELECT CASE WHEN EXISTS ("
                f"SELECT 1 FROM {xml_table_name} WHERE {xml_identity_column} = :identity"
                f") THEN 1 ELSE 0 END"
            ),
            {"identity": identity},
        ).scalar()

        if not document_exists:
            return XmlLookupResult(
                identity=identity, legacy_column=legacy_column, outcome="document_not_found"
            )

        extracted_value = conn.execute(
            text(
                f"SELECT {xml_payload_column}.value('{safe_xpath}', '{safe_cast_type}') "
                f"AS extracted_value FROM {xml_table_name} WHERE {xml_identity_column} = :identity"
            ),
            {"identity": identity},
        ).scalar()

    if extracted_value is None:
        return XmlLookupResult(
            identity=identity, legacy_column=legacy_column, outcome="field_missing"
        )
    return XmlLookupResult(
        identity=identity, legacy_column=legacy_column, outcome="found", value=str(extracted_value)
    )
