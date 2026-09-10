"""Reconciliation routes (FR-009/FR-010, spec.md User Story 3).

Compares a deployed view's live output against its `legacy_shape_capture`'s old
table, keyed by a user-designated identity column. Strictly read-only against both
connections it touches (Constitution Principle I) — every query issued here is a
plain `SELECT`; no code path in this module ever issues UPDATE/DELETE/DROP.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.connectors.mssql import ConnectionUnreachableError, build_engine
from src.db.session import get_db
from src.models.connection_config import ConnectionConfig
from src.models.deployment_log import ViewDeploymentLogEntry
from src.models.legacy_shape import LegacyShapeCapture
from src.models.legacy_view_column_rule import LegacyViewColumnRule
from src.models.reconciliation import ReconciliationRun
from src.models.view_definition import ViewDefinition, ViewDefinitionVersion
from src.services.reconciliation_engine import compare_row_sets

router = APIRouter(tags=["reconciliation"])


def _json_safe(value):
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _json_safe_row(row: dict) -> dict:
    return {k: _json_safe(v) for k, v in row.items()}


class ReconcileRequest(BaseModel):
    view_definition_version_id: uuid.UUID | None = None
    identity_column: str
    operator: str = "system-operator"


class ReconciliationOut(BaseModel):
    id: uuid.UUID
    view_definition_version_id: uuid.UUID
    identity_column: str
    outcome: str | None
    rows_matched: int
    rows_old_only: int
    rows_view_only: int
    rows_with_column_mismatch: int
    row_inflation_flagged: bool
    discrepancy_detail: list[dict]

    model_config = {"from_attributes": True}


def _resolve_version(
    db: Session, view_definition_id: uuid.UUID, version_id: uuid.UUID | None
) -> tuple[ViewDefinition, ViewDefinitionVersion]:
    definition = db.get(ViewDefinition, view_definition_id)
    if definition is None:
        raise ApiError("not_found", f"no view definition {view_definition_id}", 404)

    resolved_version_id = version_id or definition.current_version_id
    version = db.get(ViewDefinitionVersion, resolved_version_id) if resolved_version_id else None
    if version is None:
        raise ApiError(
            "not_found", f"no view_definition_version to reconcile for {view_definition_id}", 404
        )
    return definition, version


@router.post(
    "/view-definitions/{view_definition_id}/reconcile",
    response_model=ReconciliationOut,
    status_code=201,
)
def reconcile_view(
    view_definition_id: uuid.UUID, body: ReconcileRequest, db: Session = Depends(get_db)
):
    definition, version = _resolve_version(db, view_definition_id, body.view_definition_version_id)

    # contracts/api.md: "you can't reconcile a view that was only ever previewed."
    has_successful_deploy = (
        db.query(ViewDeploymentLogEntry)
        .filter(
            ViewDeploymentLogEntry.view_definition_version_id == version.id,
            ViewDeploymentLogEntry.mode == "deploy",
            ViewDeploymentLogEntry.outcome == "completed",
        )
        .first()
    )
    if has_successful_deploy is None:
        raise ApiError(
            "not_deployed",
            f"view_definition_version {version.id} has never been successfully deployed; "
            "reconciliation requires a deployed view, not just a preview",
            409,
        )

    legacy_shape = db.get(LegacyShapeCapture, definition.legacy_shape_capture_id)
    legacy_columns = [c["name"] for c in legacy_shape.columns]
    if body.identity_column not in legacy_columns:
        raise ApiError(
            "mapping_invalid",
            f"identity_column '{body.identity_column}' is not one of the legacy shape's "
            f"columns {legacy_columns}",
            422,
        )

    old_connection = db.get(ConnectionConfig, legacy_shape.connection_id)
    view_connection = db.get(ConnectionConfig, definition.target_connection_id)

    try:
        old_engine = build_engine(old_connection)
        with old_engine.connect() as conn:
            old_rows = [
                _json_safe_row(dict(row))
                for row in conn.execute(
                    text(
                        f"SELECT * FROM {legacy_shape.table_name} "
                        f"ORDER BY {body.identity_column}"
                    )
                )
                .mappings()
                .all()
            ]

        view_engine = build_engine(view_connection)
        with view_engine.connect() as conn:
            view_rows = [
                _json_safe_row(dict(row))
                for row in conn.execute(
                    text(f"SELECT * FROM {definition.name} ORDER BY {body.identity_column}")
                )
                .mappings()
                .all()
            ]
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc

    retired_columns = {
        rule.column_name
        for rule in db.query(LegacyViewColumnRule)
        .filter(
            LegacyViewColumnRule.view_definition_version_id == version.id,
            LegacyViewColumnRule.column_status == "Retired",
        )
        .all()
    }

    comparison = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column=body.identity_column,
        compare_columns=legacy_columns,
        retired_columns=retired_columns,
    )

    run = ReconciliationRun(
        id=uuid.uuid4(),
        view_definition_version_id=version.id,
        identity_column=body.identity_column,
        completed_at=datetime.now(UTC),
        outcome="completed",
        rows_matched=comparison.rows_matched,
        rows_old_only=comparison.rows_old_only,
        rows_view_only=comparison.rows_view_only,
        rows_with_column_mismatch=comparison.rows_with_column_mismatch,
        row_inflation_flagged=comparison.row_inflation_flagged,
        discrepancy_detail=comparison.discrepancy_detail,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    log_audit_event(
        action="reconciliation.run",
        operator=body.operator,
        resource="reconciliation_run",
        resource_id=run.id,
        details={
            "view_definition_id": str(view_definition_id),
            "view_definition_version_id": str(version.id),
            "identity_column": body.identity_column,
            "rows_matched": comparison.rows_matched,
            "rows_old_only": comparison.rows_old_only,
            "rows_view_only": comparison.rows_view_only,
            "rows_with_column_mismatch": comparison.rows_with_column_mismatch,
            "row_inflation_flagged": comparison.row_inflation_flagged,
        },
    )
    return run


@router.get(
    "/view-definitions/{view_definition_id}/reconciliations",
    response_model=list[ReconciliationOut],
)
def list_reconciliations(view_definition_id: uuid.UUID, db: Session = Depends(get_db)):
    runs = (
        db.query(ReconciliationRun)
        .join(
            ViewDefinitionVersion,
            ReconciliationRun.view_definition_version_id == ViewDefinitionVersion.id,
        )
        .filter(ViewDefinitionVersion.view_definition_id == view_definition_id)
        .order_by(ReconciliationRun.started_at)
        .all()
    )
    return runs


@router.get("/reconciliations/{reconciliation_id}", response_model=ReconciliationOut)
def get_reconciliation(reconciliation_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.get(ReconciliationRun, reconciliation_id)
    if run is None:
        raise ApiError("not_found", f"no reconciliation_run {reconciliation_id}", 404)
    return run
