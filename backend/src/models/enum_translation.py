import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class EnumTranslationTable(Base):
    """The stable, named identity of a reusable enum lookup (FR-006)."""

    __tablename__ = "enum_translation_table"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "enum_translation_version.id", use_alter=True, name="fk_current_translation_version"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EnumTranslationVersion(Base):
    """An immutable set of code -> translated_value entries for one version."""

    __tablename__ = "enum_translation_version"
    __table_args__ = (UniqueConstraint("enum_translation_table_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enum_translation_table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enum_translation_table.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
