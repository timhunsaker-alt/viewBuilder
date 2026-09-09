import uuid

from sqlalchemy.orm import Session

from src.models.connection_config import ConnectionConfig


class ConnectionService:
    """CRUD over connection_config. Never returns `credential_ref` to a caller
    (Constitution Principle VI) — callers that need to actually connect should load the
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
        credential_ref: str,
    ) -> ConnectionConfig:
        connection = ConnectionConfig(
            id=uuid.uuid4(),
            name=name,
            role=role,
            environment=environment,
            host=host,
            port=port,
            database=database,
            credential_ref=credential_ref,
        )
        self.db.add(connection)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def list(self) -> list[ConnectionConfig]:
        return list(self.db.query(ConnectionConfig).order_by(ConnectionConfig.name).all())

    def get(self, connection_id: uuid.UUID) -> ConnectionConfig | None:
        return self.db.get(ConnectionConfig, connection_id)
