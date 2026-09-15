import uuid

from sqlalchemy.orm import Session

from src.models.connection_config import ConnectionConfig


class ConnectionValidationError(Exception):
    """Raised when a connection_config can't be created as specified.

    Carries a stable `code` so the API layer can map it to the right error response.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ConnectionService:
    """CRUD over connection_config. Never returns `credential_ref` to a caller
    (credential-handling policy) — callers that need to actually connect should load the
    ORM row directly via `get` and pass it to src.connectors.mssql, not round-trip through
    a serialized representation.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        name: str,
        role: str,
        environment: str,
        host: str,
        port: int,
        database: str,
        auth_mode: str = "sql",
        username: str | None = None,
        credential_ref: str | None = None,
    ) -> ConnectionConfig:
        if auth_mode == "sql" and not credential_ref:
            raise ConnectionValidationError(
                "mapping_invalid", "auth_mode='sql' requires a credential_ref"
            )
        if auth_mode == "windows_integrated" and (username or credential_ref):
            raise ConnectionValidationError(
                "mapping_invalid",
                "auth_mode='windows_integrated' takes no username/credential_ref — the "
                "backend's own Windows/AD identity is used instead",
            )
        connection = ConnectionConfig(
            id=uuid.uuid4(),
            name=name,
            role=role,
            environment=environment,
            host=host,
            port=port,
            database=database,
            auth_mode=auth_mode,
            username=username if auth_mode == "sql" else None,
            credential_ref=credential_ref if auth_mode == "sql" else None,
        )
        self.db.add(connection)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def list(self) -> list[ConnectionConfig]:
        return list(self.db.query(ConnectionConfig).order_by(ConnectionConfig.name).all())

    def get(self, connection_id: uuid.UUID) -> ConnectionConfig | None:
        return self.db.get(ConnectionConfig, connection_id)
