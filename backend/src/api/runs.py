import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.connectors.mssql import ConnectionUnreachableError
from src.db.session import get_db
from src.models.mapping import MappingVersion
from src.models.run_log import RunLogEntry
from src.services.run_orchestrator import (
    MappingNotFoundError,
    ProductionConfirmationRequiredError,
    SchemaDriftError,
    WriteConstraintViolationError,
    run_mapping,
)

router = APIRouter(tags=["runs"])


class DryRunRequest(BaseModel):
    mapping_version_id: uuid.UUID | None = None
    operator: str = "system-operator"


class ExecuteRequest(BaseModel):
    mapping_version_id: uuid.UUID | None = None
    operator: str = "system-operator"
    confirm_production: bool = False


class RunLogOut(BaseModel):
    id: uuid.UUID
    mapping_version_id: uuid.UUID
    mode: str
    operator: str
    outcome: str | None
    source_rows_read: int
    target_rows_written: int
    retirement_records_written: int
    untranslatable_rows_flagged: int
    sample_rows: list
    production_confirmed: bool

    model_config = {"from_attributes": True}


@router.post("/mappings/{mapping_id}/dry-run", response_model=RunLogOut, status_code=201)
def dry_run(mapping_id: uuid.UUID, body: DryRunRequest, db: Session = Depends(get_db)):
    try:
        run_log = run_mapping(
            db, mapping_definition_id=mapping_id, mode="dry_run", operator=body.operator
        )
    except MappingNotFoundError as exc:
        raise ApiError("not_found", f"no mapping with id {mapping_id}", 404) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc
    log_audit_event(
        action="mapping.dry_run",
        operator=body.operator,
        resource="mapping_version",
        resource_id=run_log.mapping_version_id,
        version=run_log.mapping_version_id,
        details={"mapping_definition_id": str(mapping_id), "run_log_entry_id": str(run_log.id)},
    )
    return run_log


@router.post("/mappings/{mapping_id}/execute", response_model=RunLogOut, status_code=201)
def execute(mapping_id: uuid.UUID, body: ExecuteRequest, db: Session = Depends(get_db)):
    try:
        run_log = run_mapping(
            db,
            mapping_definition_id=mapping_id,
            mode="execute",
            operator=body.operator,
            confirm_production=body.confirm_production,
        )
    except MappingNotFoundError as exc:
        raise ApiError("not_found", f"no mapping with id {mapping_id}", 404) from exc
    except ProductionConfirmationRequiredError as exc:
        raise ApiError("production_confirmation_required", str(exc), 409) from exc
    except SchemaDriftError as exc:
        raise ApiError("schema_mismatch", str(exc), 422) from exc
    except WriteConstraintViolationError as exc:
        raise ApiError("write_constraint_violation", str(exc), 422) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc
    log_audit_event(
        action="mapping.execute",
        operator=body.operator,
        resource="mapping_version",
        resource_id=run_log.mapping_version_id,
        version=run_log.mapping_version_id,
        details={
            "mapping_definition_id": str(mapping_id),
            "run_log_entry_id": str(run_log.id),
            "production_confirmed": run_log.production_confirmed,
        },
    )
    return run_log


@router.get("/runs", response_model=list[RunLogOut])
def list_runs(
    mapping_definition_id: uuid.UUID | None = Query(default=None),
    mode: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(RunLogEntry)
    if mode:
        query = query.filter(RunLogEntry.mode == mode)
    if mapping_definition_id:
        version_ids = [
            row.id
            for row in db.query(MappingVersion.id)
            .filter(MappingVersion.mapping_definition_id == mapping_definition_id)
            .all()
        ]
        query = query.filter(RunLogEntry.mapping_version_id.in_(version_ids))
    return query.order_by(RunLogEntry.started_at.desc()).all()


@router.get("/runs/{run_id}", response_model=RunLogOut)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.get(RunLogEntry, run_id)
    if run is None:
        raise ApiError("not_found", f"no run with id {run_id}", 404)
    return run
