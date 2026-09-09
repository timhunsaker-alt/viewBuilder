import logging
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.enum_translation import EnumTranslationTable, EnumTranslationVersion

logger = logging.getLogger("viewbuilder.enum_translation_service")


class EnumTranslationValidationError(Exception):
    """Raised when an enum-translation table/version fails validation."""


def _validate_entries(entries: list[dict]) -> None:
    seen_codes: set[str] = set()
    for entry in entries:
        code = entry.get("code")
        if code is None or "translated_value" not in entry:
            raise EnumTranslationValidationError(
                f"entry {entry} must have both 'code' and 'translated_value'"
            )
        code = str(code)
        if code in seen_codes:
            raise EnumTranslationValidationError(
                f"duplicate code '{code}' within a single translation version"
            )
        seen_codes.add(code)


class EnumTranslationService:
    """Create/version enum-translation tables (FR-006). Every save creates a new,
    immutable version — an existing version's entries are never mutated (Constitution
    Principle II, applied identically to translation tables as to mappings).
    """

    def __init__(self, db: Session):
        self.db = db

    def create_table(self, *, name: str, entries: list[dict]) -> EnumTranslationTable:
        _validate_entries(entries)

        table = EnumTranslationTable(id=uuid.uuid4(), name=name)
        self.db.add(table)
        self.db.flush()

        version = EnumTranslationVersion(
            id=uuid.uuid4(),
            enum_translation_table_id=table.id,
            version_number=1,
            entries=entries,
        )
        self.db.add(version)
        self.db.flush()

        table.current_version_id = version.id
        self.db.commit()
        self.db.refresh(table)
        logger.info("enum_translation_table_created table_id=%s name=%s", table.id, name)
        return table

    def save_new_version(
        self, *, table_id: uuid.UUID, entries: list[dict]
    ) -> EnumTranslationVersion:
        table = self.db.get(EnumTranslationTable, table_id)
        if table is None:
            raise EnumTranslationValidationError(f"no enum translation table {table_id}")

        _validate_entries(entries)

        next_version_number = (
            self.db.query(func.max(EnumTranslationVersion.version_number))
            .filter(EnumTranslationVersion.enum_translation_table_id == table_id)
            .scalar()
            or 0
        ) + 1

        version = EnumTranslationVersion(
            id=uuid.uuid4(),
            enum_translation_table_id=table_id,
            version_number=next_version_number,
            entries=entries,
        )
        self.db.add(version)
        self.db.flush()

        table.current_version_id = version.id
        self.db.commit()
        self.db.refresh(version)
        logger.info(
            "enum_translation_version_saved table_id=%s version=%s", table_id, next_version_number
        )
        return version

    def get(self, table_id: uuid.UUID) -> EnumTranslationTable | None:
        return self.db.get(EnumTranslationTable, table_id)

    def get_version(self, version_id: uuid.UUID) -> EnumTranslationVersion | None:
        return self.db.get(EnumTranslationVersion, version_id)

    def list(self) -> list[EnumTranslationTable]:
        return list(self.db.query(EnumTranslationTable).order_by(EnumTranslationTable.name).all())
