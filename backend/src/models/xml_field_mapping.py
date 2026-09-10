import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class XmlFieldMapping(Base):
    """Per-old-table-column configuration of where a value lives in the legacy XML
    document store (FR-011). Modeled here in Phase 2 (Foundational) per data-model.md
    so the schema exists ahead of the US4 xml_lookup_service work (T046+); no XML
    lookup endpoint is implemented in this MVP checkpoint (US1 only).
    """

    __tablename__ = "xml_field_mapping"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legacy_shape_capture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("legacy_shape_capture.id"), nullable=False
    )
    xml_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("connection_config.id"), nullable=False
    )
    xml_table_name: Mapped[str] = mapped_column(String(400), nullable=False)
    xml_identity_column: Mapped[str] = mapped_column(String(200), nullable=False)
    xml_payload_column: Mapped[str] = mapped_column(String(200), nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "xml_field_mapping_version.id", use_alter=True, name="fk_current_xml_mapping_version"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class XmlFieldMappingVersion(Base):
    """An immutable set of {legacy_column, xpath, cast_type} entries for one version
    (Constitution Principle II) — not required to cover every legacy column at once
    (US4 AC4: added incrementally as columns come under investigation)."""

    __tablename__ = "xml_field_mapping_version"
    __table_args__ = (UniqueConstraint("xml_field_mapping_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    xml_field_mapping_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("xml_field_mapping.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field_paths: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
