import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

CONNECTION_ROLES = ("source", "target", "either")
CONNECTION_ENVIRONMENTS = ("dev", "test", "prod")


class ConnectionConfig(Base):
    """A named, reusable reference to a SQL Server database (source or target).

    `credential_ref` is an opaque pointer into a secrets store — the raw credential is
    never stored here and never returned by the API (Constitution Principle VI).
    """

    __tablename__ = "connection_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(*CONNECTION_ROLES, name="connection_role"), nullable=False
    )
    environment: Mapped[str] = mapped_column(
        Enum(*CONNECTION_ENVIRONMENTS, name="connection_environment"), nullable=False
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=1433)
    database: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
