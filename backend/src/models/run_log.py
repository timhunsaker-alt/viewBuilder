import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

RUN_MODES = ("dry_run", "execute")
RUN_OUTCOMES = ("completed", "partially_completed", "failed")


class RunLogEntry(Base):
    """One dry-run or execution of a specific mapping version (FR-014).

    Append-only once `completed_at` is set — re-running always creates a new entry,
    never updates a prior one (Constitution Principle I).
    """

    __tablename__ = "run_log_entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mapping_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mapping_version.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(Enum(*RUN_MODES, name="run_mode"), nullable=False)
    operator: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(
        Enum(*RUN_OUTCOMES, name="run_outcome"), nullable=True
    )
    source_rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retirement_records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    untranslatable_rows_flagged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    production_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
