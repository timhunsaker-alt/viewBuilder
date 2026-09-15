"""Writes retirement audit records into the *target* database (FR-009/FR-010).

append-only retirement policy (NON-NEGOTIABLE): retirement must never be implemented as an
in-place update or delete of the source row. This module enforces that by construction:
`source_conn` is only ever passed to `select(...)` — no `update()`/`delete()` statement
against the source table is built anywhere in this module. `target_conn` is only ever
used for a dedup `select(...)` and an insert-only `insert(...)` into the audit table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import MetaData, Table, insert, select
from sqlalchemy.engine import Connection


@dataclass
class RetirementRunResult:
    rows_considered: int = 0
    audit_records_written: int = 0
    duplicates_skipped: int = 0
    untranslatable_skipped: int = 0


def _reflect_table(conn: Connection, table_name: str) -> Table:
    schema, _, name = table_name.partition(".")
    if not name:
        schema, name = None, schema
    metadata = MetaData()
    return Table(name, metadata, schema=schema, autoload_with=conn)


def run_retirement(
    *,
    source_conn: Connection,
    target_conn: Connection,
    source_table: str,
    row_identity_column: str,
    status_column: str,
    retired_value_codes: list[str],
    reason_column: str,
    reason_translation_entries: dict[str, str],
    audit_binding: dict,
    mapping_version_id: uuid.UUID,
    dry_run: bool = False,
) -> RetirementRunResult:
    """Read source rows whose status matches `retired_value_codes` and write one
    retirement-audit record per row into the target's configured audit table.

    - Never touches the source table beyond a read-only SELECT (Principle IV).
    - Skips (does not duplicate) a row whose identity already has an audit record
      (FR-011).
    - Skips (does not guess/default) a row whose reason code has no entry in
      `reason_translation_entries` (Principle III, applied identically to retirement
      reasons as to any other enum-coded column).
    - `dry_run=True` performs the read and dedup/translation checks but writes nothing,
      for use by the dry-run preview (US4).
    """
    result = RetirementRunResult()

    source_tbl = _reflect_table(source_conn, source_table)
    audit_tbl = _reflect_table(target_conn, audit_binding["audit_table"])

    identity_col = source_tbl.c[row_identity_column]
    status_col = source_tbl.c[status_column]
    reason_col = source_tbl.c[reason_column]

    source_rows = source_conn.execute(
        select(identity_col, status_col, reason_col).where(status_col.in_(retired_value_codes))
    ).all()

    audit_identity_col = audit_tbl.c[audit_binding["row_identity_target_column"]]

    for row in source_rows:
        result.rows_considered += 1
        identity_value = str(row[0])
        reason_code = None if row[2] is None else str(row[2])

        already_retired = target_conn.execute(
            select(audit_identity_col).where(audit_identity_col == identity_value)
        ).first()
        if already_retired is not None:
            result.duplicates_skipped += 1
            continue

        translated_reason = (
            reason_translation_entries.get(reason_code) if reason_code is not None else None
        )
        if translated_reason is None:
            result.untranslatable_skipped += 1
            continue

        if dry_run:
            result.audit_records_written += 1
            continue

        insert_values = {
            audit_binding["row_identity_target_column"]: identity_value,
            audit_binding["reason_target_column"]: translated_reason,
            audit_binding["timestamp_target_column"]: datetime.now(UTC),
        }
        mapping_version_column = audit_binding.get("mapping_version_target_column")
        if mapping_version_column:
            insert_values[mapping_version_column] = str(mapping_version_id)

        target_conn.execute(insert(audit_tbl).values(**insert_values))
        result.audit_records_written += 1

    if not dry_run:
        target_conn.commit()

    return result
