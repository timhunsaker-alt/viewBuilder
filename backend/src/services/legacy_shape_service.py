"""Capture the old (wide) table's shape (FR-001) and detect drift against a live
re-introspection of it later (FR-013).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from src.connectors.mssql import get_columns
from src.models.connection_config import ConnectionConfig
from src.models.legacy_shape import LegacyShapeCapture

logger = logging.getLogger("viewbuilder.legacy_shape_service")


class LegacyShapeValidationError(Exception):
    """Raised when a legacy-shape capture is requested against configuration that
    doesn't exist (e.g. an unknown connection_id)."""


class LegacyShapeService:
    def __init__(self, db: Session):
        self.db = db

    def capture(
        self, *, name: str, connection_id: uuid.UUID, table_name: str
    ) -> LegacyShapeCapture:
        connection = self.db.get(ConnectionConfig, connection_id)
        if connection is None:
            raise LegacyShapeValidationError(f"no connection_config {connection_id}")

        # Never returns a stale/cached shape — introspects live, every time
        # (contracts/api.md POST /legacy-shapes). A ConnectionUnreachableError from
        # get_columns propagates to the caller (API layer maps it to 503).
        columns = get_columns(connection, table_name)

        capture = LegacyShapeCapture(
            id=uuid.uuid4(),
            name=name,
            connection_id=connection_id,
            table_name=table_name,
            columns=[{"name": c.name, "type": c.type, "nullable": c.nullable} for c in columns],
        )
        self.db.add(capture)
        self.db.commit()
        self.db.refresh(capture)
        logger.info("legacy_shape_captured id=%s name=%s table=%s", capture.id, name, table_name)
        return capture

    def get(self, capture_id: uuid.UUID) -> LegacyShapeCapture | None:
        return self.db.get(LegacyShapeCapture, capture_id)

    def list(self) -> list[LegacyShapeCapture]:
        return list(self.db.query(LegacyShapeCapture).order_by(LegacyShapeCapture.name).all())

    def check_drift(self, capture_id: uuid.UUID) -> dict:
        """FR-013: re-introspect the live table and compare it to what was captured.
        Never mutates the stored capture — drift is reported, not silently absorbed.
        """
        capture = self.get(capture_id)
        if capture is None:
            raise LegacyShapeValidationError(f"no legacy_shape_capture {capture_id}")
        connection = self.db.get(ConnectionConfig, capture.connection_id)
        if connection is None:
            raise LegacyShapeValidationError(f"no connection_config {capture.connection_id}")

        live_columns = get_columns(connection, capture.table_name)
        live_by_name = {c.name: c for c in live_columns}
        captured_by_name = {c["name"]: c for c in capture.columns}

        added_columns = sorted(set(live_by_name) - set(captured_by_name))
        removed_columns = sorted(set(captured_by_name) - set(live_by_name))
        retyped_columns = sorted(
            name
            for name in set(live_by_name) & set(captured_by_name)
            if live_by_name[name].type != captured_by_name[name]["type"]
        )

        drifted = bool(added_columns or removed_columns or retyped_columns)
        return {
            "drifted": drifted,
            "added_columns": added_columns,
            "removed_columns": removed_columns,
            "retyped_columns": retyped_columns,
        }
