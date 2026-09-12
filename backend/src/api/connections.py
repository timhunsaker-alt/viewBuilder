import logging
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.middleware import log_audit_event
from src.connectors.mssql import ConnectionUnreachableError, get_columns, list_tables
from src.db.session import get_db
from src.models.connection_config import (
    CONNECTION_AUTH_MODES,
    CONNECTION_ENVIRONMENTS,
    CONNECTION_ROLES,
)
from src.services.connection_service import ConnectionService, ConnectionValidationError

logger = logging.getLogger("viewbuilder")
router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionCreate(BaseModel):
    name: str
    role: str
    environment: str
    host: str
    port: int = 1433
    database: str
    auth_mode: str = "sql"
    username: str | None = None
    credential_ref: str | None = None
    operator: str = "system-operator"


class ConnectionOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    environment: str
    host: str
    port: int
    database: str
    auth_mode: str
    username: str | None
    # Deliberately no `credential_ref` field — never returned by the API.

    model_config = {"from_attributes": True}


class ColumnOut(BaseModel):
    name: str
    type: str
    nullable: bool


class SchemaOut(BaseModel):
    tables: list[str] | None = None
    columns: list[ColumnOut] | None = None


@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db)):
    return ConnectionService(db).list()


@router.post("", response_model=ConnectionOut, status_code=201)
def create_connection(body: ConnectionCreate, db: Session = Depends(get_db)):
    if body.role not in CONNECTION_ROLES:
        raise ApiError("invalid_role", f"role must be one of {CONNECTION_ROLES}", 422)
    if body.environment not in CONNECTION_ENVIRONMENTS:
        raise ApiError(
            "invalid_environment", f"environment must be one of {CONNECTION_ENVIRONMENTS}", 422
        )
    if body.auth_mode not in CONNECTION_AUTH_MODES:
        raise ApiError(
            "invalid_auth_mode", f"auth_mode must be one of {CONNECTION_AUTH_MODES}", 422
        )
    try:
        connection = ConnectionService(db).create(
            name=body.name,
            role=body.role,
            environment=body.environment,
            host=body.host,
            port=body.port,
            database=body.database,
            auth_mode=body.auth_mode,
            username=body.username,
            credential_ref=body.credential_ref,
        )
    except ConnectionValidationError as exc:
        raise ApiError(exc.code, str(exc), 422) from exc
    log_audit_event(
        action="connection.create",
        operator=body.operator,
        resource="connection_config",
        resource_id=connection.id,
        details={"name": connection.name, "auth_mode": connection.auth_mode},
    )
    return connection


@router.get("/{connection_id}/schema", response_model=SchemaOut)
def get_schema(
    connection_id: uuid.UUID,
    table: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    connection = ConnectionService(db).get(connection_id)
    if connection is None:
        raise ApiError("not_found", f"no connection with id {connection_id}", 404)

    try:
        if table:
            columns = get_columns(connection, table)
            return SchemaOut(
                columns=[ColumnOut(name=c.name, type=c.type, nullable=c.nullable) for c in columns]
            )
        tables = list_tables(connection)
        return SchemaOut(tables=tables)
    except ConnectionUnreachableError as exc:
        logger.warning(
            "connection_unreachable connection_id=%s connection_name=%s cause=%r",
            connection_id,
            connection.name,
            exc.cause,
        )
        raise ApiError(
            "connection_unreachable",
            f"could not reach connection '{connection.name}'",
            503,
            details={"cause": str(exc.cause) if exc.cause else None},
        ) from exc
