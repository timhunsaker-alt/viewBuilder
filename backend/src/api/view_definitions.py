import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.connectors.mssql import ConnectionUnreachableError
from src.db.session import get_db
from src.services.legacy_shape_service import LegacyShapeValidationError
from src.services.view_definition_service import (
    ViewDefinitionService,
    ViewDefinitionValidationError,
)
from src.services.view_deployment_service import (
    DeploymentVerificationError,
    ProductionConfirmationRequiredError,
    SchemaMismatchError,
    ViewDefinitionNotFoundError,
    deploy_view,
    preview_view,
)

router = APIRouter(prefix="/view-definitions", tags=["view-definitions"])

# contracts/api.md: `name_collision` is a conflict on the definitional identity, the
# rest are unprocessable-content-shaped validation failures.
_VALIDATION_STATUS_BY_CODE = {"name_collision": 409, "mapping_invalid": 422}


class JoinGraphEdge(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    join_type: str = "inner"


ColumnStatus = Literal["Mapped", "Retired", "Transient", "Historical"]


class ColumnMappingEntry(BaseModel):
    legacy_column: str
    source_table: str | None = None
    # Not required to be non-empty at the Pydantic level for a Retired column (the
    # view casts NULL for those instead) — the real "must have a source unless
    # Retired" rule is enforced in view_definition_service.validate_column_mappings,
    # since Pydantic alone can't see column_status when validating this field.
    source_column_or_expression: str = ""
    column_status: ColumnStatus = "Mapped"
    # When set, this column is enum-coded: the deployed view wraps its source value in
    # a CASE translating each of this enum_translation_version's entries (ddl_generator
    # module docstring) instead of reading the raw code straight through. Existence is
    # checked in view_definition_service.validate_enum_references, not here — same
    # reasoning as column_status/source_column_or_expression above.
    enum_translation_version_id: uuid.UUID | None = None
    notes: str | None = None


class ViewDefinitionCreate(BaseModel):
    name: str
    legacy_shape_capture_id: uuid.UUID
    target_connection_id: uuid.UUID
    join_graph: list[JoinGraphEdge]
    column_mappings: list[ColumnMappingEntry]
    operator: str = "system-operator"


class ViewDefinitionVersionCreate(BaseModel):
    join_graph: list[JoinGraphEdge]
    column_mappings: list[ColumnMappingEntry]
    operator: str = "system-operator"


class PreviewOrDeployRequest(BaseModel):
    view_definition_version_id: uuid.UUID | None = None
    confirm_production: bool = False
    operator: str = "system-operator"


class ViewDefinitionOut(BaseModel):
    id: uuid.UUID
    name: str
    legacy_shape_capture_id: uuid.UUID
    target_connection_id: uuid.UUID
    current_version_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ViewDefinitionVersionOut(BaseModel):
    id: uuid.UUID
    view_definition_id: uuid.UUID
    version_number: int
    join_graph: list[dict]
    column_mappings: list[dict]
    generated_sql: str

    model_config = {"from_attributes": True}


class LegacyViewColumnRuleOut(BaseModel):
    id: uuid.UUID
    view_definition_version_id: uuid.UUID
    legacy_table_name: str
    compatibility_view_name: str
    column_name: str
    column_status: str
    expected_null_flag: bool
    notes: str | None

    model_config = {"from_attributes": True}


class ViewDeploymentLogOut(BaseModel):
    id: uuid.UUID
    view_definition_version_id: uuid.UUID
    mode: str
    operator: str
    outcome: str | None
    sample_rows: list[dict]
    column_diff: dict | None
    production_confirmed: bool
    generated_sql: str

    model_config = {"from_attributes": True}


def _deployment_log_out(db: Session, log) -> ViewDeploymentLogOut:
    """Attaches the version's `generated_sql` (contracts/api.md: preview/deploy return
    a view_deployment_log-shaped payload that includes the generated SQL) — the SQL
    itself lives on `view_definition_version`, not on the log entry."""
    from src.models.view_definition import ViewDefinitionVersion  # noqa: PLC0415

    version = db.get(ViewDefinitionVersion, log.view_definition_version_id)
    return ViewDeploymentLogOut(
        id=log.id,
        view_definition_version_id=log.view_definition_version_id,
        mode=log.mode,
        operator=log.operator,
        outcome=log.outcome,
        sample_rows=log.sample_rows,
        column_diff=log.column_diff,
        production_confirmed=log.production_confirmed,
        generated_sql=version.generated_sql if version else "",
    )


def _raise_validation(exc: ViewDefinitionValidationError):
    status = _VALIDATION_STATUS_BY_CODE.get(exc.code, 422)
    raise ApiError(exc.code, str(exc), status) from exc


@router.get("", response_model=list[ViewDefinitionOut])
def list_view_definitions(db: Session = Depends(get_db)):
    return ViewDefinitionService(db).list()


@router.post("", response_model=ViewDefinitionOut, status_code=201)
def create_view_definition(body: ViewDefinitionCreate, db: Session = Depends(get_db)):
    try:
        definition = ViewDefinitionService(db).create_view_definition(
            name=body.name,
            legacy_shape_capture_id=body.legacy_shape_capture_id,
            target_connection_id=body.target_connection_id,
            join_graph=[edge.model_dump() for edge in body.join_graph],
            column_mappings=[m.model_dump(mode="json") for m in body.column_mappings],
        )
    except ViewDefinitionValidationError as exc:
        _raise_validation(exc)
    log_audit_event(
        action="view_definition.create",
        operator=body.operator,
        resource="view_definition",
        resource_id=definition.id,
        version=1,
        details={"name": definition.name},
    )
    return definition


@router.get("/{view_definition_id}", response_model=ViewDefinitionOut)
def get_view_definition(view_definition_id: uuid.UUID, db: Session = Depends(get_db)):
    definition = ViewDefinitionService(db).get(view_definition_id)
    if definition is None:
        raise ApiError("not_found", f"no view definition with id {view_definition_id}", 404)
    return definition


@router.get("/{view_definition_id}/versions", response_model=list[ViewDefinitionVersionOut])
def list_view_definition_versions(view_definition_id: uuid.UUID, db: Session = Depends(get_db)):
    return ViewDefinitionService(db).list_versions(view_definition_id)


@router.get("/{view_definition_id}/column-rules", response_model=list[LegacyViewColumnRuleOut])
def list_view_definition_column_rules(view_definition_id: uuid.UUID, db: Session = Depends(get_db)):
    """The append-only `legacy_view_column_rule` history for this definition — every
    version's save writes a fresh row per legacy column, so this can show how a
    column's status changed over time, not just its current state."""
    return ViewDefinitionService(db).list_column_rules(view_definition_id)


@router.post(
    "/{view_definition_id}/versions", response_model=ViewDefinitionVersionOut, status_code=201
)
def create_view_definition_version(
    view_definition_id: uuid.UUID, body: ViewDefinitionVersionCreate, db: Session = Depends(get_db)
):
    try:
        version = ViewDefinitionService(db).save_new_version(
            view_definition_id=view_definition_id,
            join_graph=[edge.model_dump() for edge in body.join_graph],
            column_mappings=[m.model_dump(mode="json") for m in body.column_mappings],
        )
    except ViewDefinitionValidationError as exc:
        _raise_validation(exc)
    log_audit_event(
        action="view_definition.version.create",
        operator=body.operator,
        resource="view_definition_version",
        resource_id=version.id,
        version=version.version_number,
        details={"view_definition_id": str(view_definition_id)},
    )
    return version


@router.post("/{view_definition_id}/preview", response_model=ViewDeploymentLogOut, status_code=201)
def preview_view_definition(
    view_definition_id: uuid.UUID, body: PreviewOrDeployRequest, db: Session = Depends(get_db)
):
    try:
        log = preview_view(
            db,
            view_definition_id=view_definition_id,
            view_definition_version_id=body.view_definition_version_id,
            operator=body.operator,
        )
    except ViewDefinitionNotFoundError as exc:
        raise ApiError("not_found", str(exc), 404) from exc
    except SchemaMismatchError as exc:
        raise ApiError("schema_mismatch", str(exc), 409) from exc
    except LegacyShapeValidationError as exc:
        raise ApiError("not_found", str(exc), 404) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc
    log_audit_event(
        action="view_definition.preview",
        operator=body.operator,
        resource="view_deployment_log",
        resource_id=log.id,
        details={"view_definition_id": str(view_definition_id), "mode": "preview"},
    )
    return _deployment_log_out(db, log)


@router.post("/{view_definition_id}/deploy", response_model=ViewDeploymentLogOut, status_code=201)
def deploy_view_definition(
    view_definition_id: uuid.UUID, body: PreviewOrDeployRequest, db: Session = Depends(get_db)
):
    try:
        log = deploy_view(
            db,
            view_definition_id=view_definition_id,
            view_definition_version_id=body.view_definition_version_id,
            operator=body.operator,
            confirm_production=body.confirm_production,
        )
    except ViewDefinitionNotFoundError as exc:
        raise ApiError("not_found", str(exc), 404) from exc
    except SchemaMismatchError as exc:
        raise ApiError("schema_mismatch", str(exc), 409) from exc
    except LegacyShapeValidationError as exc:
        raise ApiError("not_found", str(exc), 404) from exc
    except ProductionConfirmationRequiredError as exc:
        raise ApiError("production_confirmation_required", str(exc), 409) from exc
    except DeploymentVerificationError as exc:
        # T053: contracts/api.md's error-code catalogue for this feature does not
        # include `deploy_verification_failed` — the closest documented code for "a
        # shape no longer matches what was expected" is `schema_mismatch` (already used
        # above for pre-deploy drift); reusing it here for the post-deploy verification
        # failure (SC-002) keeps this endpoint's error codes within the documented set
        # rather than introducing an undocumented one.
        raise ApiError("schema_mismatch", str(exc), 409) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc
    log_audit_event(
        action="view_definition.deploy",
        operator=body.operator,
        resource="view_deployment_log",
        resource_id=log.id,
        details={"view_definition_id": str(view_definition_id), "mode": "deploy"},
    )
    return _deployment_log_out(db, log)


@router.get("/{view_definition_id}/deployments", response_model=list[ViewDeploymentLogOut])
def list_view_deployments(
    view_definition_id: uuid.UUID, mode: str | None = None, db: Session = Depends(get_db)
):
    from src.models.deployment_log import ViewDeploymentLogEntry  # noqa: PLC0415
    from src.models.view_definition import ViewDefinitionVersion  # noqa: PLC0415

    query = (
        db.query(ViewDeploymentLogEntry)
        .join(
            ViewDefinitionVersion,
            ViewDeploymentLogEntry.view_definition_version_id == ViewDefinitionVersion.id,
        )
        .filter(ViewDefinitionVersion.view_definition_id == view_definition_id)
    )
    if mode is not None:
        query = query.filter(ViewDeploymentLogEntry.mode == mode)
    logs = query.order_by(ViewDeploymentLogEntry.started_at).all()
    return [_deployment_log_out(db, log) for log in logs]
