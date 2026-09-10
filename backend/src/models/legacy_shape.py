import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class LegacyShapeCapture(Base):
    """A snapshot of the old (wide) table's column list/order/types (FR-001).

    Re-capturing the same table is always allowed and never invalidates a prior
    capture — drift is detected by re-introspecting `table_name` live and comparing it
    against a specific capture's stored `columns` (FR-013), not by mutating this row.
    """

    __tablename__ = "legacy_shape_capture"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("connection_config.id"), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(400), nullable=False)
    columns: Mapped[list] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
