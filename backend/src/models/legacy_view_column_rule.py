import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

VALID_COLUMN_STATUSES = ("Mapped", "Retired", "Transient", "Historical")


class LegacyViewColumnRule(Base):
    """One row per legacy-shape column, per view_definition_version — an append-only
    governance record of how that column is currently treated:

    - Mapped: has a real, live source in the new schema (the normal case).
    - Retired: no longer sourced from the new schema at all; the view outputs
      CAST(NULL AS <legacy column's own type>) for it (see ddl_generator.py) so
      consumers still get the correct data type, just no data.
    - Transient: has a real source today but is expected to go away/change soon.
    - Historical: reflects data that is fixed/no-longer-updated, kept for reporting.

    Never updated once written — a new version's save writes a fresh set of rows
    (Constitution Principle II: immutable per-version record), so the history of how
    a column's status changed over time is preserved rather than overwritten.
    """

    __tablename__ = "legacy_view_column_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    view_definition_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("view_definition_version.id"), nullable=False
    )
    legacy_table_name: Mapped[str] = mapped_column(String(400), nullable=False)
    compatibility_view_name: Mapped[str] = mapped_column(String(200), nullable=False)
    column_name: Mapped[str] = mapped_column(String(200), nullable=False)
    column_status: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_null_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
