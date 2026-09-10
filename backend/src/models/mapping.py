import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

MAPPING_KINDS = ("column_mapping", "retirement")


class MappingDefinition(Base):
    """The stable, named identity of a mapping across all its versions."""

    __tablename__ = "mapping_definition"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(Enum(*MAPPING_KINDS, name="mapping_kind"), nullable=False)
    source_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("connection_config.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String(400), nullable=False)
    target_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("connection_config.id"), nullable=False
    )
    target_table: Mapped[str] = mapped_column(String(400), nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("mapping_version.id", use_alter=True, name="fk_current_version"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MappingVersion(Base):
    """An immutable snapshot of a mapping's column links (Constitution Principle II).

    Once created, a version's `column_links`/`retirement_config` are never mutated — an
    edit always creates a new version referencing the same `mapping_definition_id`.
    """

    __tablename__ = "mapping_version"
    __table_args__ = (UniqueConstraint("mapping_definition_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mapping_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mapping_definition.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column_links: Mapped[list] = mapped_column(JSON, nullable=False)
    retirement_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_identity_column: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
