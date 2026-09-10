"""XML field mapping & lookup routes (FR-011/FR-012, spec.md User Story 4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.connectors.mssql import ConnectionUnreachableError
from src.db.session import get_db
from src.models.connection_config import ConnectionConfig
from src.models.legacy_shape import LegacyShapeCapture
from src.models.xml_field_mapping import XmlFieldMapping, XmlFieldMappingVersion
from src.services.xml_lookup_service import (
    DEFAULT_CAST_TYPE,
    XmlFieldNotConfiguredError,
    lookup_xml_field,
)

router = APIRouter(prefix="/xml-field-mappings", tags=["xml-field-mappings"])


class FieldPathEntry(BaseModel):
    legacy_column: str
    xpath: str
    cast_type: str = DEFAULT_CAST_TYPE


class XmlFieldMappingCreate(BaseModel):
    legacy_shape_capture_id: uuid.UUID
    xml_connection_id: uuid.UUID
    xml_table_name: str
    xml_identity_column: str
    xml_payload_column: str
    field_paths: list[FieldPathEntry] = []
    operator: str = "system-operator"


class XmlFieldMappingVersionCreate(BaseModel):
    field_paths: list[FieldPathEntry]
    operator: str = "system-operator"


class LookupRequest(BaseModel):
    identity: str
    legacy_column: str


class XmlFieldMappingOut(BaseModel):
    id: uuid.UUID
    legacy_shape_capture_id: uuid.UUID
    xml_connection_id: uuid.UUID
    xml_table_name: str
    xml_identity_column: str
    xml_payload_column: str
    current_version_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class XmlFieldMappingVersionOut(BaseModel):
    id: uuid.UUID
    xml_field_mapping_id: uuid.UUID
    version_number: int
    field_paths: list[dict]

    model_config = {"from_attributes": True}


class XmlLookupResultOut(BaseModel):
    identity: str
    legacy_column: str
    outcome: str
    value: str | None = None


@router.post("", response_model=XmlFieldMappingOut, status_code=201)
def create_xml_field_mapping(body: XmlFieldMappingCreate, db: Session = Depends(get_db)):
    legacy_shape = db.get(LegacyShapeCapture, body.legacy_shape_capture_id)
    if legacy_shape is None:
        raise ApiError("not_found", f"no legacy_shape_capture {body.legacy_shape_capture_id}", 404)
    connection = db.get(ConnectionConfig, body.xml_connection_id)
    if connection is None:
        raise ApiError("not_found", f"no connection_config {body.xml_connection_id}", 404)

    mapping = XmlFieldMapping(
        id=uuid.uuid4(),
        legacy_shape_capture_id=body.legacy_shape_capture_id,
        xml_connection_id=body.xml_connection_id,
        xml_table_name=body.xml_table_name,
        xml_identity_column=body.xml_identity_column,
        xml_payload_column=body.xml_payload_column,
    )
    db.add(mapping)
    db.flush()

    version = XmlFieldMappingVersion(
        id=uuid.uuid4(),
        xml_field_mapping_id=mapping.id,
        version_number=1,
        field_paths=[fp.model_dump() for fp in body.field_paths],
    )
    db.add(version)
    db.flush()
    mapping.current_version_id = version.id
    db.commit()
    db.refresh(mapping)

    log_audit_event(
        action="xml_field_mapping.create",
        operator=body.operator,
        resource="xml_field_mapping",
        resource_id=mapping.id,
        version=1,
        details={"xml_table_name": mapping.xml_table_name},
    )
    return mapping


@router.get("", response_model=list[XmlFieldMappingOut])
def list_xml_field_mappings(db: Session = Depends(get_db)):
    return list(db.query(XmlFieldMapping).order_by(XmlFieldMapping.xml_table_name).all())


@router.get("/{mapping_id}", response_model=XmlFieldMappingOut)
def get_xml_field_mapping(mapping_id: uuid.UUID, db: Session = Depends(get_db)):
    mapping = db.get(XmlFieldMapping, mapping_id)
    if mapping is None:
        raise ApiError("not_found", f"no xml_field_mapping {mapping_id}", 404)
    return mapping


@router.post("/{mapping_id}/versions", response_model=XmlFieldMappingVersionOut, status_code=201)
def create_xml_field_mapping_version(
    mapping_id: uuid.UUID, body: XmlFieldMappingVersionCreate, db: Session = Depends(get_db)
):
    """US4 AC4: add/edit `field_paths` entries (e.g. for a newly-investigated column)
    as a new, immutable version — never mutates a prior version's row (Principle II)."""
    mapping = db.get(XmlFieldMapping, mapping_id)
    if mapping is None:
        raise ApiError("not_found", f"no xml_field_mapping {mapping_id}", 404)

    next_version_number = (
        db.query(func.max(XmlFieldMappingVersion.version_number))
        .filter(XmlFieldMappingVersion.xml_field_mapping_id == mapping_id)
        .scalar()
        or 0
    ) + 1

    version = XmlFieldMappingVersion(
        id=uuid.uuid4(),
        xml_field_mapping_id=mapping_id,
        version_number=next_version_number,
        field_paths=[fp.model_dump() for fp in body.field_paths],
    )
    db.add(version)
    db.flush()
    mapping.current_version_id = version.id
    db.commit()
    db.refresh(version)

    log_audit_event(
        action="xml_field_mapping.version.create",
        operator=body.operator,
        resource="xml_field_mapping_version",
        resource_id=version.id,
        version=version.version_number,
        details={"xml_field_mapping_id": str(mapping_id)},
    )
    return version


@router.post("/{mapping_id}/lookup", response_model=XmlLookupResultOut)
def run_xml_lookup(mapping_id: uuid.UUID, body: LookupRequest, db: Session = Depends(get_db)):
    mapping = db.get(XmlFieldMapping, mapping_id)
    if mapping is None:
        raise ApiError("not_found", f"no xml_field_mapping {mapping_id}", 404)

    version = (
        db.get(XmlFieldMappingVersion, mapping.current_version_id)
        if mapping.current_version_id
        else None
    )
    if version is None:
        raise ApiError(
            "mapping_invalid", f"xml_field_mapping {mapping_id} has no version configured yet", 422
        )

    connection = db.get(ConnectionConfig, mapping.xml_connection_id)
    if connection is None:
        raise ApiError("not_found", f"no connection_config {mapping.xml_connection_id}", 404)

    try:
        result = lookup_xml_field(
            connection,
            xml_table_name=mapping.xml_table_name,
            xml_identity_column=mapping.xml_identity_column,
            xml_payload_column=mapping.xml_payload_column,
            identity=body.identity,
            legacy_column=body.legacy_column,
            field_paths=version.field_paths,
        )
    except XmlFieldNotConfiguredError as exc:
        raise ApiError("mapping_invalid", str(exc), 422) from exc
    except ConnectionUnreachableError as exc:
        raise ApiError("connection_unreachable", str(exc), 503) from exc

    log_audit_event(
        action="xml_field_mapping.lookup",
        operator="system-operator",
        resource="xml_field_mapping",
        resource_id=mapping_id,
        details={
            "identity": body.identity,
            "legacy_column": body.legacy_column,
            "outcome": result.outcome,
        },
    )
    return XmlLookupResultOut(
        identity=result.identity,
        legacy_column=result.legacy_column,
        outcome=result.outcome,
        value=result.value,
    )
