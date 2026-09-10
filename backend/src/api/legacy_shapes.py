import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.connectors.mssql import ConnectionUnreachableError
from src.db.session import get_db
from src.services.legacy_shape_service import LegacyShapeService, LegacyShapeValidationError

router = APIRouter(prefix="/legacy-shapes", tags=["legacy-shapes"])


class LegacyShapeCreate(BaseModel):
    name: str
    connection_id: uuid.UUID
    table_name: str
    operator: str = "system-operator"


class LegacyShapeColumnOut(BaseModel):
    name: str
    type: str
    nullable: bool


class LegacyShapeOut(BaseModel):
    id: uuid.UUID
    name: str
    connection_id: uuid.UUID
    table_name: str
    columns: list[dict]

    model_config = {"from_attributes": True}


class DriftOut(BaseModel):
    drifted: bool
    added_columns: list[str]
    removed_columns: list[str]
    retyped_columns: list[str]


@router.get("", response_model=list[LegacyShapeOut])
def list_legacy_shapes(db: Session = Depends(get_db)):
    return LegacyShapeService(db).list()


@router.post("", response_model=LegacyShapeOut, status_code=201)
def create_legacy_shape(body: LegacyShapeCreate, db: Session = Depends(get_db)):
    try:
        capture = LegacyShapeService(db).capture(
            name=body.name, connection_id=body.connection_id, table_name=body.table_name
        )
    except LegacyShapeValidationError as exc:
        raise ApiError("mapping_invalid", str(exc), 422) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc
    log_audit_event(
        action="legacy_shape.capture",
        operator=body.operator,
        resource="legacy_shape_capture",
        resource_id=capture.id,
        details={"name": capture.name, "table_name": capture.table_name},
    )
    return capture


@router.get("/{capture_id}", response_model=LegacyShapeOut)
def get_legacy_shape(capture_id: uuid.UUID, db: Session = Depends(get_db)):
    capture = LegacyShapeService(db).get(capture_id)
    if capture is None:
        raise ApiError("not_found", f"no legacy shape capture with id {capture_id}", 404)
    return capture


@router.get("/{capture_id}/drift", response_model=DriftOut)
def get_legacy_shape_drift(capture_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        drift = LegacyShapeService(db).check_drift(capture_id)
    except LegacyShapeValidationError as exc:
        raise ApiError("not_found", str(exc), 404) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc
    return drift
