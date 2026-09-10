"""Join-graph reachability validation (FR-002), column-mapping completeness
validation (FR-004), and versioning (FR-007) for compatibility view definitions —
mirrors `mapping_service.py` from 001-sql-view-builder.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.legacy_shape import LegacyShapeCapture
from src.models.view_definition import ViewDefinition, ViewDefinitionVersion
from src.services.ddl_generator import DdlGenerationError, build_create_view_sql

logger = logging.getLogger("viewbuilder.view_definition_service")


class ViewDefinitionValidationError(Exception):
    """Raised when a view definition (or a new version of one) fails validation.

    Carries a stable `code` so the API layer can map it to the right error response
    per contracts/api.md (`name_collision`, `mapping_invalid`).
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def validate_join_graph(tables: set[str], join_graph: list[dict]) -> None:
    """FR-002: every table referenced (by a join edge or a column mapping's
    `source_table`) MUST be reachable from every other via the configured joins — no
    orphan tables. A single-table view (no joins needed) is always valid.
    """
    if len(tables) <= 1:
        return

    adjacency: dict[str, set[str]] = {t: set() for t in tables}
    for edge in join_graph:
        left, right = edge.get("left_table"), edge.get("right_table")
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)

    # Find every connected component (there should be exactly one). Iterating tables
    # in sorted order makes the choice of "which component is the odd one out"
    # deterministic rather than depending on Python's arbitrary set-iteration order.
    unvisited = set(tables)
    components: list[set[str]] = []
    for candidate in sorted(tables):
        if candidate not in unvisited:
            continue
        component = {candidate}
        stack = [candidate]
        unvisited.discard(candidate)
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor in unvisited:
                    unvisited.discard(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(component)

    if len(components) <= 1:
        return

    # The largest component is treated as "the graph"; every smaller component is
    # reported as orphaned from it (ties broken toward the component containing the
    # alphabetically-first table, for determinism).
    components.sort(key=lambda c: (-len(c), sorted(c)))
    main_component = components[0]
    orphans = sorted(tables - main_component)
    if orphans:
        raise ViewDefinitionValidationError(
            "mapping_invalid",
            f"join_graph leaves tables unreachable from the others: {orphans} (FR-002)",
        )


def validate_column_mappings(legacy_columns: list[str], column_mappings: list[dict]) -> None:
    """FR-004: every legacy-shape column MUST have a mapping entry; block (rather than
    silently omit/reorder) otherwise, with a clear list of what's missing.
    """
    mapped = {m.get("legacy_column") for m in column_mappings}
    missing = [c for c in legacy_columns if c not in mapped]
    if missing:
        raise ViewDefinitionValidationError(
            "mapping_invalid",
            f"column_mappings does not cover every legacy-shape column; "
            f"missing: {missing} (FR-004)",
        )
    unknown = sorted(mapped - set(legacy_columns))
    if unknown:
        raise ViewDefinitionValidationError(
            "mapping_invalid",
            f"column_mappings references columns not present in the legacy shape: {unknown}",
        )


def _referenced_tables(join_graph: list[dict], column_mappings: list[dict]) -> set[str]:
    tables: set[str] = set()
    for edge in join_graph:
        tables.add(edge["left_table"])
        tables.add(edge["right_table"])
    for mapping in column_mappings:
        if mapping.get("source_table"):
            tables.add(mapping["source_table"])
    return tables


class ViewDefinitionService:
    """Create/version compatibility view definitions. Every save creates a new,
    immutable `view_definition_version` row — an existing version is never mutated
    (Constitution Principle II).
    """

    def __init__(self, db: Session):
        self.db = db

    def _validate_and_generate_sql(
        self,
        *,
        name: str,
        legacy_shape: LegacyShapeCapture,
        join_graph: list[dict],
        column_mappings: list[dict],
    ) -> str:
        if name == legacy_shape.table_name:
            raise ViewDefinitionValidationError(
                "name_collision",
                f"view name '{name}' must not equal the legacy shape's own table_name "
                f"'{legacy_shape.table_name}' (research.md §5) — SQL Server cannot have a "
                "table and a view share one name in the same schema.",
            )

        legacy_columns = [c["name"] for c in legacy_shape.columns]
        validate_column_mappings(legacy_columns, column_mappings)
        tables = _referenced_tables(join_graph, column_mappings)
        validate_join_graph(tables, join_graph)

        try:
            return build_create_view_sql(
                view_name=name,
                legacy_columns=legacy_columns,
                join_graph=join_graph,
                column_mappings=column_mappings,
            )
        except DdlGenerationError as exc:
            raise ViewDefinitionValidationError("mapping_invalid", str(exc)) from exc

    def create_view_definition(
        self,
        *,
        name: str,
        legacy_shape_capture_id: uuid.UUID,
        target_connection_id: uuid.UUID,
        join_graph: list[dict],
        column_mappings: list[dict],
    ) -> ViewDefinition:
        legacy_shape = self.db.get(LegacyShapeCapture, legacy_shape_capture_id)
        if legacy_shape is None:
            raise ViewDefinitionValidationError(
                "mapping_invalid", f"no legacy_shape_capture {legacy_shape_capture_id}"
            )

        generated_sql = self._validate_and_generate_sql(
            name=name,
            legacy_shape=legacy_shape,
            join_graph=join_graph,
            column_mappings=column_mappings,
        )

        definition = ViewDefinition(
            id=uuid.uuid4(),
            name=name,
            legacy_shape_capture_id=legacy_shape_capture_id,
            target_connection_id=target_connection_id,
        )
        self.db.add(definition)
        self.db.flush()

        version = ViewDefinitionVersion(
            id=uuid.uuid4(),
            view_definition_id=definition.id,
            version_number=1,
            join_graph=join_graph,
            column_mappings=column_mappings,
            generated_sql=generated_sql,
        )
        self.db.add(version)
        self.db.flush()

        definition.current_version_id = version.id
        self.db.commit()
        self.db.refresh(definition)
        logger.info("view_definition_created id=%s name=%s", definition.id, name)
        return definition

    def save_new_version(
        self,
        *,
        view_definition_id: uuid.UUID,
        join_graph: list[dict],
        column_mappings: list[dict],
    ) -> ViewDefinitionVersion:
        definition = self.db.get(ViewDefinition, view_definition_id)
        if definition is None:
            raise ViewDefinitionValidationError(
                "mapping_invalid", f"no view_definition {view_definition_id}"
            )
        legacy_shape = self.db.get(LegacyShapeCapture, definition.legacy_shape_capture_id)

        generated_sql = self._validate_and_generate_sql(
            name=definition.name,
            legacy_shape=legacy_shape,
            join_graph=join_graph,
            column_mappings=column_mappings,
        )

        next_version_number = (
            self.db.query(func.max(ViewDefinitionVersion.version_number))
            .filter(ViewDefinitionVersion.view_definition_id == view_definition_id)
            .scalar()
            or 0
        ) + 1

        version = ViewDefinitionVersion(
            id=uuid.uuid4(),
            view_definition_id=view_definition_id,
            version_number=next_version_number,
            join_graph=join_graph,
            column_mappings=column_mappings,
            generated_sql=generated_sql,
        )
        self.db.add(version)
        self.db.flush()

        definition.current_version_id = version.id
        self.db.commit()
        self.db.refresh(version)
        logger.info(
            "view_definition_version_saved view_definition_id=%s version=%s",
            view_definition_id,
            next_version_number,
        )
        return version

    def list_versions(self, view_definition_id: uuid.UUID) -> list[ViewDefinitionVersion]:
        return list(
            self.db.query(ViewDefinitionVersion)
            .filter(ViewDefinitionVersion.view_definition_id == view_definition_id)
            .order_by(ViewDefinitionVersion.version_number)
            .all()
        )

    def get(self, view_definition_id: uuid.UUID) -> ViewDefinition | None:
        return self.db.get(ViewDefinition, view_definition_id)

    def list(self) -> list[ViewDefinition]:
        return list(self.db.query(ViewDefinition).order_by(ViewDefinition.name).all())
