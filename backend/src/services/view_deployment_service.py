"""Preview (zero-DDL) and deploy (real `CREATE OR ALTER VIEW`) orchestration for a
compatibility view definition version (FR-005/FR-006/FR-008).

Mirrors `run_orchestrator.py` from 001-sql-view-builder: this module is the seam where
schema-drift re-checking (FR-013), the production-confirmation gate (Constitution
Principle VII), and `view_deployment_log` persistence all happen. Preview NEVER issues
DDL — it runs the view's `SELECT` body capped with `TOP N` as an ordinary read-only
query (Constitution Principle I: reviewable, reversible — a bad preview leaves nothing
behind to revert).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.connectors.mssql import build_engine, get_columns
from src.models.connection_config import ConnectionConfig
from src.models.deployment_log import ViewDeploymentLogEntry
from src.models.legacy_shape import LegacyShapeCapture
from src.models.view_definition import ViewDefinition, ViewDefinitionVersion
from src.services.ddl_generator import build_select_sql
from src.services.legacy_shape_service import LegacyShapeService

SAMPLE_ROW_CAP = 5


class ViewDefinitionNotFoundError(Exception):
    """Raised when the view definition or the requested/current version can't be found."""


class SchemaMismatchError(Exception):
    """FR-013: the legacy shape has drifted since it was captured — block rather than
    silently preview/deploy against a shape that no longer matches reality."""


class ProductionConfirmationRequiredError(Exception):
    """Deploying (CREATE OR ALTER VIEW) against a `prod`-tagged connection without
    `confirm_production=True` (Constitution Principle VII, mirrors 001's FR-016)."""


class DeploymentVerificationError(Exception):
    """The view was deployed, but its introspected column list/order does not match
    the legacy shape it was supposed to reproduce (SC-002) — surfaced loudly rather
    than reported as a clean success."""


def _json_safe(value):
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _json_safe_row(row: dict) -> dict:
    return {k: _json_safe(v) for k, v in row.items()}


@dataclass
class _Resolved:
    definition: ViewDefinition
    version: ViewDefinitionVersion
    legacy_shape: LegacyShapeCapture
    connection: ConnectionConfig


def _resolve(
    db: Session, *, view_definition_id: uuid.UUID, view_definition_version_id: uuid.UUID | None
) -> _Resolved:
    definition = db.get(ViewDefinition, view_definition_id)
    if definition is None:
        raise ViewDefinitionNotFoundError(f"no view_definition {view_definition_id}")

    version_id = view_definition_version_id or definition.current_version_id
    version = db.get(ViewDefinitionVersion, version_id) if version_id else None
    if version is None:
        raise ViewDefinitionNotFoundError(
            f"no view_definition_version to preview/deploy for {view_definition_id}"
        )

    legacy_shape = db.get(LegacyShapeCapture, definition.legacy_shape_capture_id)
    connection = db.get(ConnectionConfig, definition.target_connection_id)

    drift = LegacyShapeService(db).check_drift(definition.legacy_shape_capture_id)
    if drift["drifted"]:
        raise SchemaMismatchError(
            f"legacy shape '{legacy_shape.name}' has drifted since it was captured: "
            f"{drift} (FR-013)"
        )

    return _Resolved(
        definition=definition, version=version, legacy_shape=legacy_shape, connection=connection
    )


def preview_view(
    db: Session,
    *,
    view_definition_id: uuid.UUID,
    view_definition_version_id: uuid.UUID | None = None,
    operator: str = "system-operator",
) -> ViewDeploymentLogEntry:
    resolved = _resolve(
        db,
        view_definition_id=view_definition_id,
        view_definition_version_id=view_definition_version_id,
    )
    legacy_columns = [c["name"] for c in resolved.legacy_shape.columns]
    select_sql = build_select_sql(
        legacy_columns=legacy_columns,
        join_graph=resolved.version.join_graph,
        column_mappings=resolved.version.column_mappings,
    )
    preview_sql = f"SELECT TOP {SAMPLE_ROW_CAP} * FROM (\n{select_sql}\n) AS preview_query"

    engine = build_engine(resolved.connection)
    with engine.connect() as conn:
        rows = conn.execute(text(preview_sql)).mappings().all()
    sample_rows = [_json_safe_row(dict(row)) for row in rows]

    log = ViewDeploymentLogEntry(
        id=uuid.uuid4(),
        view_definition_version_id=resolved.version.id,
        mode="preview",
        operator=operator,
        completed_at=datetime.now(UTC),
        outcome="completed",
        sample_rows=sample_rows,
        column_diff=None,
        production_confirmed=False,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def deploy_view(
    db: Session,
    *,
    view_definition_id: uuid.UUID,
    view_definition_version_id: uuid.UUID | None = None,
    operator: str = "system-operator",
    confirm_production: bool = False,
) -> ViewDeploymentLogEntry:
    resolved = _resolve(
        db,
        view_definition_id=view_definition_id,
        view_definition_version_id=view_definition_version_id,
    )
    touches_production = resolved.connection.environment == "prod"
    if touches_production and not confirm_production:
        raise ProductionConfirmationRequiredError(
            f"view definition '{resolved.definition.name}' targets a production connection; "
            "confirm_production=true is required to deploy (Constitution Principle VII)"
        )

    engine = build_engine(resolved.connection)
    with engine.connect() as conn:
        conn.execute(text(resolved.version.generated_sql))
        conn.commit()

    legacy_columns = [c["name"] for c in resolved.legacy_shape.columns]
    deployed_columns = [c.name for c in get_columns(resolved.connection, resolved.definition.name)]
    if deployed_columns != legacy_columns:
        raise DeploymentVerificationError(
            f"deployed view '{resolved.definition.name}' columns {deployed_columns} do not "
            f"exactly match the legacy shape's columns {legacy_columns} (SC-002)"
        )

    log = ViewDeploymentLogEntry(
        id=uuid.uuid4(),
        view_definition_version_id=resolved.version.id,
        mode="deploy",
        operator=operator,
        completed_at=datetime.now(UTC),
        outcome="completed",
        sample_rows=[],
        column_diff=None,
        production_confirmed=bool(touches_production and confirm_production),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
