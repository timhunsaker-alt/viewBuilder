import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.db.session import get_db
from src.services.enum_translation_service import (
    EnumTranslationService,
    EnumTranslationValidationError,
)

router = APIRouter(prefix="/enum-translations", tags=["enum-translations"])


class EnumEntry(BaseModel):
    code: str
    translated_value: str


class EnumTranslationCreate(BaseModel):
    name: str
    entries: list[EnumEntry]


class EnumTranslationVersionCreate(BaseModel):
    entries: list[EnumEntry]


class EnumTranslationOut(BaseModel):
    id: uuid.UUID
    name: str
    current_version_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class EnumTranslationVersionOut(BaseModel):
    id: uuid.UUID
    enum_translation_table_id: uuid.UUID
    version_number: int
    entries: list[dict]

    model_config = {"from_attributes": True}


@router.get("", response_model=list[EnumTranslationOut])
def list_enum_translations(db: Session = Depends(get_db)):
    return EnumTranslationService(db).list()


@router.post("", response_model=EnumTranslationOut, status_code=201)
def create_enum_translation(body: EnumTranslationCreate, db: Session = Depends(get_db)):
    try:
        return EnumTranslationService(db).create_table(
            name=body.name, entries=[e.model_dump() for e in body.entries]
        )
    except EnumTranslationValidationError as exc:
        raise ApiError("enum_translation_invalid", str(exc), 422) from exc


@router.get("/{table_id}", response_model=EnumTranslationOut)
def get_enum_translation(table_id: uuid.UUID, db: Session = Depends(get_db)):
    table = EnumTranslationService(db).get(table_id)
    if table is None:
        raise ApiError("not_found", f"no enum translation table with id {table_id}", 404)
    return table


@router.post("/{table_id}/versions", response_model=EnumTranslationVersionOut, status_code=201)
def create_enum_translation_version(
    table_id: uuid.UUID, body: EnumTranslationVersionCreate, db: Session = Depends(get_db)
):
    try:
        return EnumTranslationService(db).save_new_version(
            table_id=table_id, entries=[e.model_dump() for e in body.entries]
        )
    except EnumTranslationValidationError as exc:
        raise ApiError("enum_translation_invalid", str(exc), 422) from exc
