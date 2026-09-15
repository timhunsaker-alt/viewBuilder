import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class ViewDefinition(Base):
    """The stable, named identity of a compatibility view across all its versions
    (mirrors MappingDefinition/MappingVersion from 001-sql-view-builder).

    `name` is also the name the deployed SQL VIEW is created under (FR-006) and is
    validated (at the service layer) to differ from the referenced legacy shape's own
    `table_name` (research.md §5 — a view can never share the old table's exact name
    while both exist).
    """

    __tablename__ = "view_definition"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    legacy_shape_capture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("legacy_shape_capture.id"), nullable=False
    )
    target_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("connection_config.id"), nullable=False
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("view_definition_version.id", use_alter=True, name="fk_current_view_version"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ViewDefinitionVersion(Base):
    """An immutable snapshot of a view definition's join graph + column mappings +
    generated SQL (immutable-version policy). A version, once referenced by any
    `view_deployment_log` entry, MUST NOT be mutated by any update endpoint.
    """

    __tablename__ = "view_definition_version"
    __table_args__ = (UniqueConstraint("view_definition_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    view_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("view_definition.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    join_graph: Mapped[list] = mapped_column(JSON, nullable=False)
    column_mappings: Mapped[list] = mapped_column(JSON, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
