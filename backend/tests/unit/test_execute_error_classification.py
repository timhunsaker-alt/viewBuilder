"""Regression test: a genuine target-database constraint violation (NOT NULL/PK/FK)
during execute must be classified as a write_constraint_violation, never mislabeled as
connection_unreachable (the connection and query were both fine — the row was invalid).

Found by hand against a real deployed MS SQL Server (a NOT NULL target column omitted
from a mapping surfaced as a 503 connection_unreachable instead of a 422). Reproduced
here with two in-memory SQLite engines substituted for build_engine's normal MS SQL
Server engines, so this runs without any live SQL Server / ODBC driver.
"""

import os
import uuid

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from src.models.connection_config import ConnectionConfig
from src.services.mapping_service import MappingService
from src.services.run_orchestrator import WriteConstraintViolationError, run_mapping
from tests.conftest import requires_postgres


@requires_postgres
def test_target_not_null_violation_is_not_mislabeled_as_connection_unreachable(
    monkeypatch, db_session
):
    os.environ["VIEWBUILDER_CRED_ERRCLASSSRC"] = "unused"
    os.environ["VIEWBUILDER_CRED_ERRCLASSTGT"] = "unused"
    source_conn_row = ConnectionConfig(
        id=uuid.uuid4(),
        name=f"err-class-source-{uuid.uuid4().hex[:8]}",
        role="either",
        environment="dev",
        host="localhost",
        port=1433,
        database="irrelevant",
        credential_ref="errclasssrc",
    )
    target_conn_row = ConnectionConfig(
        id=uuid.uuid4(),
        name=f"err-class-target-{uuid.uuid4().hex[:8]}",
        role="either",
        environment="dev",
        host="localhost",
        port=1433,
        database="irrelevant",
        credential_ref="errclasstgt",
    )
    db_session.add_all([source_conn_row, target_conn_row])
    db_session.commit()

    source_engine = create_engine("sqlite:///:memory:")
    target_engine = create_engine("sqlite:///:memory:")

    source_metadata = MetaData()
    Table(
        "legacy_customer",
        source_metadata,
        Column("customer_id", Integer, primary_key=True),
        Column("full_name", String),
    )
    source_metadata.create_all(source_engine)
    with source_engine.begin() as conn:
        conn.execute(
            source_metadata.tables["legacy_customer"].insert(),
            [{"customer_id": 1, "full_name": "Ada Lovelace"}],
        )

    target_metadata = MetaData()
    Table(
        "target_customer",
        target_metadata,
        Column("id", Integer, primary_key=True),
        Column("display_name", String),
        Column("created_at", String, nullable=False),  # intentionally left unmapped below
    )
    target_metadata.create_all(target_engine)

    engines_by_connection_id = {
        source_conn_row.id: source_engine,
        target_conn_row.id: target_engine,
    }

    # `from src.connectors.mssql import build_engine` in run_orchestrator.py binds a
    # separate name at import time — both bindings must be patched: the schema-drift
    # pre-flight check goes through src.connectors.mssql.get_columns (which calls the
    # original module's build_engine), while the actual read/write engines are built
    # via run_orchestrator's own imported build_engine name.
    fake_build_engine = lambda config: engines_by_connection_id[config.id]  # noqa: E731
    monkeypatch.setattr("src.connectors.mssql.build_engine", fake_build_engine)
    monkeypatch.setattr("src.services.run_orchestrator.build_engine", fake_build_engine)

    mapping = MappingService(db_session).create_mapping(
        name=f"not-null-violation-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=source_conn_row.id,
        source_table="legacy_customer",
        target_connection_id=target_conn_row.id,
        target_table="target_customer",
        column_links=[
            {"sourceColumn": "customer_id", "targetColumn": "id"},
            {"sourceColumn": "full_name", "targetColumn": "display_name"},
            # "created_at" is NOT NULL on the target and deliberately left unmapped.
        ],
        row_identity_column="customer_id",
    )

    try:
        run_mapping(db_session, mapping_definition_id=mapping.id, mode="execute")
        raise AssertionError("expected a WriteConstraintViolationError")
    except WriteConstraintViolationError:
        pass  # the fix under test: this must NOT surface as ConnectionUnreachableError
