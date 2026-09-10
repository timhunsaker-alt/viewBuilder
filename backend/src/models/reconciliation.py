import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

RECONCILIATION_OUTCOMES = ("completed", "partially_completed", "failed")


class ReconciliationRun(Base):
    """One comparison between a deployed view version and its legacy_shape_capture's
    old table (FR-009/FR-010). Modeled here in Phase 2 (Foundational) per data-model.md
    so the schema exists ahead of the US3 reconciliation_engine work (T036+); no
    reconciliation endpoint is implemented in this MVP checkpoint (US1 only).
    """

    __tablename__ = "reconciliation_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    view_definition_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("view_definition_version.id"), nullable=False
    )
    identity_column: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(
        Enum(*RECONCILIATION_OUTCOMES, name="reconciliation_outcome"), nullable=True
    )
    rows_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_old_only: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_view_only: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_with_column_mismatch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_inflation_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discrepancy_detail: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
