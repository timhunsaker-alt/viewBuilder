import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.db.session import get_db
from src.services.mapping_service import MappingService, MappingValidationError

router = APIRouter(prefix="/mappings", tags=["mappings"])


class ColumnLink(BaseModel):
    sourceColumn: str
    targetColumn: str
    enumTranslationVersionId: uuid.UUID | None = None


class MappingCreate(BaseModel):
    name: str
    kind: str
    source_connection_id: uuid.UUID
    source_table: str
    target_connection_id: uuid.UUID
    target_table: str
    column_links: list[ColumnLink]
    row_identity_column: str
    retirement_config: dict | None = None
    operator: str = "system-operator"


class MappingVersionCreate(BaseModel):
    column_links: list[ColumnLink]
    row_identity_column: str | None = None
    retirement_config: dict | None = None
    operator: str = "system-operator"


class MappingOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    source_connection_id: uuid.UUID
    source_table: str
    target_connection_id: uuid.UUID
    target_table: str
    current_version_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class MappingVersionOut(BaseModel):
    id: uuid.UUID
    mapping_definition_id: uuid.UUID
    version_number: int
    column_links: list[dict]
    retirement_config: dict | None
    row_identity_column: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[MappingOut])
def list_mappings(db: Session = Depends(get_db)):
    return MappingService(db).list()


@router.post("", response_model=MappingOut, status_code=201)
def create_mapping(body: MappingCreate, db: Session = Depends(get_db)):
    try:
        mapping = MappingService(db).create_mapping(
            name=body.name,
            kind=body.kind,
            source_connection_id=body.source_connection_id,
            source_table=body.source_table,
            target_connection_id=body.target_connection_id,
            target_table=body.target_table,
            column_links=[link.model_dump(exclude_none=True) for link in body.column_links],
            row_identity_column=body.row_identity_column,
            retirement_config=body.retirement_config,
        )
    except MappingValidationError as exc:
        raise ApiError("mapping_invalid", str(exc), 422) from exc
    log_audit_event(
        action="mapping.create",
        operator=body.operator,
        resource="mapping_definition",
        resource_id=mapping.id,
        version=1,
        details={"name": mapping.name, "kind": mapping.kind},
    )
    return mapping


@router.get("/{mapping_id}", response_model=MappingOut)
def get_mapping(mapping_id: uuid.UUID, db: Session = Depends(get_db)):
    mapping = MappingService(db).get(mapping_id)
    if mapping is None:
        raise ApiError("not_found", f"no mapping with id {mapping_id}", 404)
    return mapping


@router.get("/{mapping_id}/versions", response_model=list[MappingVersionOut])
def list_mapping_versions(mapping_id: uuid.UUID, db: Session = Depends(get_db)):
    return MappingService(db).list_versions(mapping_id)


@router.post("/{mapping_id}/versions", response_model=MappingVersionOut, status_code=201)
def create_mapping_version(
    mapping_id: uuid.UUID, body: MappingVersionCreate, db: Session = Depends(get_db)
):
    try:
        version = MappingService(db).save_new_version(
            mapping_definition_id=mapping_id,
            column_links=[link.model_dump(exclude_none=True) for link in body.column_links],
            row_identity_column=body.row_identity_column,
            retirement_config=body.retirement_config,
        )
    except MappingValidationError as exc:
        raise ApiError("mapping_invalid", str(exc), 422) from exc
    log_audit_event(
        action="mapping.version.create",
        operator=body.operator,
        resource="mapping_version",
        resource_id=version.id,
        version=version.version_number,
        details={"mapping_definition_id": str(mapping_id)},
    )
    return version
