"""Dry-run preview (US4) and real execution (US5) orchestration.

Delegates all translation logic to mapping_engine (US2) and all retirement-audit
writing to retirement_writer (US3) — this module only handles: reading source rows for
plain column mappings, capping/collecting a sample, counting, writing target rows
(execute only, never on dry_run), the production-confirmation gate (FR-016), the
pre-flight schema-drift check (FR-015), and persisting the run_log_entry (FR-014).

Per data-model.md's run_log_entry field notes, `target_rows_written` and
`retirement_records_written` are always persisted as 0 for `mode="dry_run"` — those
fields mean "actually written". A caller wanting the dry-run "would write" count derives
it as `source_rows_read - untranslatable_rows_flagged` (Constitution Principle I: a
dry-run performs zero writes, so persisting a non-zero write count under that mode would
misrepresent what happened).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import MetaData, Table, insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from src.connectors.mssql import ConnectionUnreachableError, build_engine, get_columns
from src.models.connection_config import ConnectionConfig
from src.models.enum_translation import EnumTranslationVersion
from src.models.mapping import MappingDefinition, MappingVersion
from src.models.run_log import RunLogEntry
from src.services.mapping_engine import load_translation_entries, translate_row
from src.services.retirement_writer import run_retirement

SAMPLE_ROW_CAP = 5


class MappingNotFoundError(Exception):
    """Raised when the mapping definition or its current version cannot be found."""


class ProductionConfirmationRequiredError(Exception):
    """FR-016: execute against a connection tagged `prod` without `confirm_production=True`."""


class SchemaDriftError(Exception):
    """FR-015: a mapped table/column no longer exists (or is missing) at execute time."""


@dataclass
class OrchestrationResult:
    source_rows_read: int = 0
    target_rows_written: int = 0
    retirement_records_written: int = 0
    untranslatable_rows_flagged: int = 0
    sample_rows: list = field(default_factory=list)


def _json_safe(value):
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _json_safe_row(row: dict) -> dict:
    return {k: _json_safe(v) for k, v in row.items()}


def _reflect_table(conn: Connection, table_name: str) -> Table:
    schema, _, name = table_name.partition(".")
    if not name:
        schema, name = None, schema
    metadata = MetaData()
    return Table(name, metadata, schema=schema, autoload_with=conn)


def run_column_mapping(
    *,
    source_conn: Connection,
    target_conn: Connection,
    source_table: str,
    target_table: str,
    column_links: list[dict],
    translation_entries: dict[str, dict[str, str]],
    dry_run: bool,
) -> OrchestrationResult:
    """Read every row from `source_table`, translate it via mapping_engine, and (unless
    `dry_run`) insert the translated row into `target_table`. A row with any
    untranslatable column is never written — it is counted and skipped in full,
    matching what a preceding dry-run would have predicted (FR-008, US5 AC3).
    """
    result = OrchestrationResult()
    source_tbl = _reflect_table(source_conn, source_table)
    source_rows = source_conn.execute(select(source_tbl)).mappings().all()

    target_tbl = None if dry_run else _reflect_table(target_conn, target_table)

    for row in source_rows:
        result.source_rows_read += 1
        row_dict = dict(row)
        translation = translate_row(row_dict, column_links, translation_entries)

        if not translation.fully_translatable:
            result.untranslatable_rows_flagged += 1
            if len(result.sample_rows) < SAMPLE_ROW_CAP:
                result.sample_rows.append(
                    {
                        "source": _json_safe_row(row_dict),
                        "target": None,
                        "untranslatable_columns": translation.untranslatable_columns,
                    }
                )
            continue

        if not dry_run:
            target_conn.execute(insert(target_tbl).values(**translation.target_row))
        result.target_rows_written += 1
        if len(result.sample_rows) < SAMPLE_ROW_CAP:
            result.sample_rows.append(
                {
                    "source": _json_safe_row(row_dict),
                    "target": _json_safe_row(translation.target_row),
                    "untranslatable_columns": [],
                }
            )

    if not dry_run:
        target_conn.commit()

    return result


def _load_flat_translation_entries(db: Session, version_id) -> dict[str, str]:
    if not version_id:
        return {}
    version = db.get(EnumTranslationVersion, uuid.UUID(str(version_id)))
    if version is None:
        return {}
    return {str(entry["code"]): entry["translated_value"] for entry in version.entries}


def _check_schema_drift(
    *,
    source_connection: ConnectionConfig,
    target_connection: ConnectionConfig,
    definition: MappingDefinition,
    version: MappingVersion,
) -> None:
    """FR-015: re-introspect the live source/target schemas referenced by this mapping
    version and fail loudly, before any write, if something referenced is now missing.
    """
    source_columns = {c.name for c in get_columns(source_connection, definition.source_table)}

    if definition.kind == "retirement":
        rc = version.retirement_config
        required_source = {rc["status_column"], rc["reason_column"], version.row_identity_column}
        missing_source = sorted(required_source - source_columns)

        audit_binding = rc["audit_binding"]
        target_columns = {
            c.name for c in get_columns(target_connection, audit_binding["audit_table"])
        }
        required_target = {
            v for k, v in audit_binding.items() if k.endswith("_target_column") and v
        }
        missing_target = sorted(required_target - target_columns)
    else:
        required_source = {link["sourceColumn"] for link in version.column_links}
        missing_source = sorted(required_source - source_columns)

        target_columns = {c.name for c in get_columns(target_connection, definition.target_table)}
        required_target = {link["targetColumn"] for link in version.column_links}
        missing_target = sorted(required_target - target_columns)

    if missing_source or missing_target:
        raise SchemaDriftError(
            f"mapping '{definition.name}' references columns no longer present: "
            f"missing source columns {missing_source}, missing target columns {missing_target}"
        )


def run_mapping(
    db: Session,
    *,
    mapping_definition_id: uuid.UUID,
    mode: str,
    operator: str = "system-operator",
    confirm_production: bool = False,
) -> RunLogEntry:
    """Dry-run (`mode="dry_run"`) or execute (`mode="execute"`) a mapping's current
    version, and persist the resulting run_log_entry (FR-014).
    """
    definition = db.get(MappingDefinition, mapping_definition_id)
    if definition is None or definition.current_version_id is None:
        raise MappingNotFoundError(f"no mapping definition {mapping_definition_id}")
    version = db.get(MappingVersion, definition.current_version_id)

    source_connection = db.get(ConnectionConfig, definition.source_connection_id)
    target_connection = db.get(ConnectionConfig, definition.target_connection_id)

    touches_production = "prod" in (source_connection.environment, target_connection.environment)
    if mode == "execute" and touches_production and not confirm_production:
        raise ProductionConfirmationRequiredError(
            f"mapping '{definition.name}' touches a production connection; "
            "confirm_production=true is required to execute (FR-016)"
        )

    if mode == "execute":
        _check_schema_drift(
            source_connection=source_connection,
            target_connection=target_connection,
            definition=definition,
            version=version,
        )

    source_engine = build_engine(source_connection)
    target_engine = build_engine(target_connection)

    try:
        with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
            if definition.kind == "retirement":
                rc = version.retirement_config
                reason_entries = _load_flat_translation_entries(
                    db, rc.get("reason_translation_version_id")
                )
                retirement_result = run_retirement(
                    source_conn=source_conn,
                    target_conn=target_conn,
                    source_table=definition.source_table,
                    row_identity_column=version.row_identity_column,
                    status_column=rc["status_column"],
                    retired_value_codes=rc["retired_value_codes"],
                    reason_column=rc["reason_column"],
                    reason_translation_entries=reason_entries,
                    audit_binding=rc["audit_binding"],
                    mapping_version_id=version.id,
                    dry_run=(mode == "dry_run"),
                )
                result = OrchestrationResult(
                    source_rows_read=retirement_result.rows_considered,
                    target_rows_written=0,
                    retirement_records_written=retirement_result.audit_records_written,
                    untranslatable_rows_flagged=retirement_result.untranslatable_skipped,
                )
            else:
                translation_entries = load_translation_entries(db, version.column_links)
                result = run_column_mapping(
                    source_conn=source_conn,
                    target_conn=target_conn,
                    source_table=definition.source_table,
                    target_table=definition.target_table,
                    column_links=version.column_links,
                    translation_entries=translation_entries,
                    dry_run=(mode == "dry_run"),
                )
    except ConnectionUnreachableError:
        raise
    except (DBAPIError, OperationalError) as exc:
        # A failure actually establishing/using the DB connection (as opposed to a
        # schema-drift/production-confirmation failure already raised above, or a bug
        # in the mapping/retirement logic itself) is reported the same way
        # get_columns()/list_tables() report it elsewhere.
        raise ConnectionUnreachableError(
            f"{source_connection.name} / {target_connection.name}", cause=exc
        ) from exc

    persisted_target_rows_written = 0 if mode == "dry_run" else result.target_rows_written
    persisted_retirement_records_written = (
        0 if mode == "dry_run" else result.retirement_records_written
    )
    outcome = "completed" if result.untranslatable_rows_flagged == 0 else "partially_completed"

    run_log = RunLogEntry(
        id=uuid.uuid4(),
        mapping_version_id=version.id,
        mode=mode,
        operator=operator,
        completed_at=datetime.now(UTC),
        outcome=outcome,
        source_rows_read=result.source_rows_read,
        target_rows_written=persisted_target_rows_written,
        retirement_records_written=persisted_retirement_records_written,
        untranslatable_rows_flagged=result.untranslatable_rows_flagged,
        sample_rows=result.sample_rows,
        production_confirmed=bool(touches_production and confirm_production),
    )
    db.add(run_log)
    db.commit()
    db.refresh(run_log)
    return run_log
