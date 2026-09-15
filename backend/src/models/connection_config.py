import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base

CONNECTION_ROLES = ("source", "target", "either")
CONNECTION_ENVIRONMENTS = ("dev", "test", "prod")
# "sql": classic SQL Server login (username + a secret resolved via credential_ref).
# "windows_integrated": the backend process's own Windows/AD identity authenticates to
# SQL Server (on-prem Windows Integrated Security, ODBC `Trusted_Connection=yes`) — a
# single fixed service-account identity, not per-end-user delegation (see research.md
# §6: true per-user Kerberos constrained delegation was evaluated and rejected as not
# buildable/verifiable from this Python/Linux backend). No credential_ref/username is
# needed or stored for this mode; every operator's own actions are still attributed to
# them via the existing audit log (operator field on every mutating endpoint), not via
# the SQL Server connection identity.
CONNECTION_AUTH_MODES = ("sql", "windows_integrated")


class ConnectionConfig(Base):
    """A named, reusable reference to a SQL Server database (source or target).

    `credential_ref` is an opaque pointer into a secrets store — the raw credential is
    never stored here and never returned by the API (credential-handling policy). It is
    only meaningful (and required) when `auth_mode="sql"`; `windows_integrated`
    connections need neither `username` nor `credential_ref`.
    """

    __tablename__ = "connection_config"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    auth_mode: Mapped[str] = mapped_column(
        Enum(*CONNECTION_AUTH_MODES, name="connection_auth_mode"), nullable=False, default="sql"
    )
    # The actual SQL login name — kept separate from `credential_ref` (the opaque
    # secret-store pointer), since the two are conceptually different (a login name is
    # not itself a secret) and previously (incorrectly) conflated by reusing
    # credential_ref as the literal UID. Nullable because windows_integrated
    # connections have no SQL login at all.
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
