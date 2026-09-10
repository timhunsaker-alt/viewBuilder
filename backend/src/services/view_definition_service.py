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
from src.models.legacy_view_column_rule import VALID_COLUMN_STATUSES, LegacyViewColumnRule
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
    silently omit/reorder) otherwise, with a clear list of what's missing. A column
    marked `column_status="Retired"` is exempt from needing a real source expression
    (the view casts NULL for it instead, per ddl_generator) — every other status
    (including the default, "Mapped") still requires one, since there's no other way
    the view could produce that column's value.
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

    for m in column_mappings:
        status = m.get("column_status") or "Mapped"
        if status not in VALID_COLUMN_STATUSES:
            raise ViewDefinitionValidationError(
                "mapping_invalid",
                f"column '{m.get('legacy_column')}' has unknown column_status '{status}'; "
                f"must be one of {VALID_COLUMN_STATUSES}",
            )

    unsourced = [
        m.get("legacy_column")
        for m in column_mappings
        if (m.get("column_status") or "Mapped") != "Retired"
        and not (m.get("source_column_or_expression") or "").strip()
    ]
    if unsourced:
        raise ViewDefinitionValidationError(
            "mapping_invalid",
            f"column_mappings missing a source expression for non-retired columns: "
            f"{unsourced} (FR-004) — mark a column Retired if it has no live source",
        )


def compute_column_diff(previous_columns: list[str], new_columns: list[str]) -> dict:
    """US2 AC3 / T034: given the ordered column list a previously-live deployed version
    produced and the ordered column list the version about to be deployed produces,
    report which columns were added, removed, or reordered relative to what's live —
    surfaced on the deploy's `view_deployment_log.column_diff` (data-model.md
    §view_deployment_log) rather than silently deploying over a shape change.

    `reordered` reports the columns common to both sides, in their new relative order,
    whenever that relative order differs from before; it is an empty list when nothing
    moved (including the common case where the two column lists are identical).
    """
    previous_set = set(previous_columns)
    new_set = set(new_columns)

    added = [c for c in new_columns if c not in previous_set]
    removed = [c for c in previous_columns if c not in new_set]

    common_previous_order = [c for c in previous_columns if c in new_set]
    common_new_order = [c for c in new_columns if c in previous_set]
    reordered = common_new_order if common_previous_order != common_new_order else []

    return {"added": added, "removed": removed, "reordered": reordered}


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

        legacy_column_names = [c["name"] for c in legacy_shape.columns]
        validate_column_mappings(legacy_column_names, column_mappings)
        tables = _referenced_tables(join_graph, column_mappings)
        validate_join_graph(tables, join_graph)

        try:
            return build_create_view_sql(
                view_name=name,
                legacy_columns=legacy_shape.columns,
                join_graph=join_graph,
                column_mappings=column_mappings,
            )
        except DdlGenerationError as exc:
            raise ViewDefinitionValidationError("mapping_invalid", str(exc)) from exc

    def _write_column_rules(
        self,
        *,
        legacy_shape: LegacyShapeCapture,
        view_name: str,
        version: ViewDefinitionVersion,
        column_mappings: list[dict],
    ) -> None:
        """Writes one `legacy_view_column_rule` row per legacy column for this
        version — an append-only governance record (never updated) of what status
        each column was under in this exact version, so a later audit can see how
        that changed over time rather than only the current state.
        """
        for mapping in column_mappings:
            status = mapping.get("column_status") or "Mapped"
            self.db.add(
                LegacyViewColumnRule(
                    id=uuid.uuid4(),
                    view_definition_version_id=version.id,
                    legacy_table_name=legacy_shape.table_name,
                    compatibility_view_name=view_name,
                    column_name=mapping["legacy_column"],
                    column_status=status,
                    expected_null_flag=(status == "Retired"),
                    notes=mapping.get("notes"),
                )
            )
        self.db.commit()

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
        self._write_column_rules(
            legacy_shape=legacy_shape,
            view_name=name,
            version=version,
            column_mappings=column_mappings,
        )
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
        self._write_column_rules(
            legacy_shape=legacy_shape,
            view_name=definition.name,
            version=version,
            column_mappings=column_mappings,
        )
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

    def list_column_rules(self, view_definition_id: uuid.UUID) -> list[LegacyViewColumnRule]:
        return list(
            self.db.query(LegacyViewColumnRule)
            .join(
                ViewDefinitionVersion,
                LegacyViewColumnRule.view_definition_version_id == ViewDefinitionVersion.id,
            )
            .filter(ViewDefinitionVersion.view_definition_id == view_definition_id)
            .order_by(LegacyViewColumnRule.created_at, LegacyViewColumnRule.column_name)
            .all()
        )

    def get(self, view_definition_id: uuid.UUID) -> ViewDefinition | None:
        return self.db.get(ViewDefinition, view_definition_id)

    def list(self) -> list[ViewDefinition]:
        return list(self.db.query(ViewDefinition).order_by(ViewDefinition.name).all())
