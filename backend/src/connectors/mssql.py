"""MS SQL Server connection management: environment-tagged connection resolution,
opaque credential lookup, and schema introspection.

Constitution Principle VI: this module is the only place raw connection strings are
assembled; `credential_ref` resolves to a secret value here and that value never leaves
this module (callers get a live SQLAlchemy engine/inspector, never the raw string).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, Inspector
from sqlalchemy.inspection import inspect

from src.models.connection_config import ConnectionConfig


class ConnectionUnreachableError(Exception):
    """Raised when a configured SQL Server connection cannot be established."""

    def __init__(self, connection_name: str, cause: Exception | None = None):
        self.connection_name = connection_name
        self.cause = cause
        super().__init__(f"Could not reach connection '{connection_name}': {cause}")


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    nullable: bool


def resolve_credential(credential_ref: str) -> str:
    """Resolve an opaque credential reference to its secret value.

    v1 uses environment-variable-backed secrets (`VIEWBUILDER_CRED_<ref>`); this is the
    single seam to swap in a real secrets manager later without touching callers.
    """
    env_key = f"VIEWBUILDER_CRED_{credential_ref.upper()}"
    value = os.environ.get(env_key)
    if value is None:
        raise ConnectionUnreachableError(
            credential_ref, cause=ValueError(f"no credential found for ref '{credential_ref}'")
        )
    return value


def build_engine(config: ConnectionConfig) -> Engine:
    password = resolve_credential(config.credential_ref)
    odbc_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={config.host},{config.port};"
        f"DATABASE={config.database};"
        f"UID={config.credential_ref};PWD={password};"
        "TrustServerCertificate=yes;"
    )
    connection_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_str)}"
    try:
        return create_engine(connection_url, pool_pre_ping=True, future=True)
    except Exception as exc:  # pragma: no cover - defensive, create_engine rarely raises
        raise ConnectionUnreachableError(config.name, cause=exc) from exc


def get_inspector(config: ConnectionConfig) -> Inspector:
    engine = build_engine(config)
    try:
        return inspect(engine)
    except Exception as exc:
        raise ConnectionUnreachableError(config.name, cause=exc) from exc


def list_tables(config: ConnectionConfig) -> list[str]:
    inspector = get_inspector(config)
    try:
        tables = []
        for schema in inspector.get_schema_names():
            if schema in ("sys", "INFORMATION_SCHEMA", "guest"):
                continue
            for table in inspector.get_table_names(schema=schema):
                tables.append(f"{schema}.{table}")
        return sorted(tables)
    except Exception as exc:
        raise ConnectionUnreachableError(config.name, cause=exc) from exc


def get_columns(config: ConnectionConfig, table: str) -> list[ColumnInfo]:
    schema, _, table_name = table.partition(".")
    if not table_name:
        schema, table_name = None, schema
    inspector = get_inspector(config)
    try:
        raw_columns = inspector.get_columns(table_name, schema=schema)
    except Exception as exc:
        raise ConnectionUnreachableError(config.name, cause=exc) from exc
    return [
        ColumnInfo(name=col["name"], type=str(col["type"]), nullable=col.get("nullable", True))
        for col in raw_columns
    ]


def table_exists(config: ConnectionConfig, table: str) -> bool:
    return table in list_tables(config)
