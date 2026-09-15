import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

DEPLOYMENT_MODES = ("preview", "deploy")
DEPLOYMENT_OUTCOMES = ("completed", "failed")


class ViewDeploymentLogEntry(Base):
    """One preview or deploy of a specific view_definition_version (FR-005/FR-008).

    Analogous to 001's `run_log_entry` but for DDL rather than row-copy: `mode=preview`
    never executes DDL (read-only preview policy) — it only runs the generated SELECT
    as a read-only sample query; `mode=deploy` actually executes `CREATE OR ALTER VIEW`.
    """

    __tablename__ = "view_deployment_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    view_definition_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("view_definition_version.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(
        Enum(*DEPLOYMENT_MODES, name="deployment_mode"), nullable=False
    )
    operator: Mapped[str] = mapped_column(default="system-operator")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(
        Enum(*DEPLOYMENT_OUTCOMES, name="deployment_outcome"), nullable=True
    )
    sample_rows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    column_diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    production_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
