"""Builds the `CREATE OR ALTER VIEW` SQL (and the underlying plain `SELECT`) for a
compatibility view definition, preserving the legacy shape's exact column order
(FR-006). This is pure, dependency-free SQL text assembly — no database connection is
opened here; callers execute (or preview) the resulting text elsewhere.

Join graph shape (research.md §4): a list of
`{left_table, left_column, right_table, right_column, join_type}` edges, where
`join_type` is `"inner"` or `"left"`. Column mapping shape (data-model.md
§view_definition_version): a list of
`{legacy_column, source_table, source_column_or_expression, column_status?, notes?}`
entries, one per legacy column. When `source_table` is set, `source_column_or_expression`
is treated as a bare column name on that table and is qualified with the table's alias.
When `source_table` is `None`, `source_column_or_expression` is used verbatim as a raw
SQL expression (e.g. a multi-table expression the caller has already qualified itself).

Every column, regardless of status, is wrapped in `CAST(... AS <legacy column's own
type>)` so the view's output always matches the old table's declared type — even when
the new-schema source column happens to already be the same type, casting is a no-op
and therefore always safe to apply unconditionally. A column whose `column_status` is
`"Retired"` ignores whatever source is configured and instead emits
`CAST(NULL AS <type>)`, so the view keeps its promised shape/types for a column the new
schema no longer sources, without fabricating data.
"""

from __future__ import annotations

import re
from collections import deque

VALID_JOIN_TYPES = ("inner", "left")
VALID_COLUMN_STATUSES = ("Mapped", "Retired", "Transient", "Historical")

# SQLAlchemy's str(type) rendering for a collated MS SQL string column looks like
# `NVARCHAR(200) COLLATE "SQL_Latin1_General_CP1_CI_AS"` — a COLLATE clause is not
# valid syntax inside a T-SQL CAST(... AS <type>) target (COLLATE only applies to a
# column definition or an expression directly), so it must be stripped before use.
_COLLATE_CLAUSE = re.compile(r"\s+COLLATE\s+\"[^\"]*\"", re.IGNORECASE)


class DdlGenerationError(Exception):
    """Raised when a join graph / column mapping cannot be turned into valid SQL —
    e.g. a referenced table isn't reachable, or a legacy column has no mapping entry.
    Callers are expected to have already run the completeness/reachability validation
    in `view_definition_service` before calling here; this is a defensive backstop.
    """


def cast_type(sql_type: str) -> str:
    """A legacy column's introspected type string, cleaned down to a bare type
    specification usable inside `CAST(expr AS <this>)`."""
    return _COLLATE_CLAUSE.sub("", sql_type).strip()


def _alias_for(table: str) -> str:
    """`dbo.loan_application` -> `loan_application`. Assumes table base names are
    unique across the tables referenced by one view definition (true for this
    feature's scope: a handful of new-schema tables per compatibility view)."""
    return table.rpartition(".")[2] or table


def _build_join_order(
    tables: set[str], join_graph: list[dict], *, root: str
) -> tuple[list[str], dict[tuple[str, str], dict]]:
    """Returns (visiting order starting from `root`, edge lookup keyed by the
    (from_table, to_table) pair actually used to join `to_table` in). Raises
    DdlGenerationError if any table in `tables` is unreachable from `root`.
    """
    adjacency: dict[str, list[tuple[str, dict]]] = {t: [] for t in tables}
    for edge in join_graph:
        left, right = edge["left_table"], edge["right_table"]
        if left not in adjacency or right not in adjacency:
            continue
        adjacency[left].append((right, edge))
        adjacency.setdefault(right, [])
        # Store a mirrored edge for traversal in either direction; the ON clause
        # itself always uses the original left/right columns as authored.
        adjacency[right].append((left, edge))

    if not tables:
        return [], {}

    visited = {root}
    order = [root]
    edge_used: dict[tuple[str, str], dict] = {}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for neighbor, edge in adjacency.get(current, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            order.append(neighbor)
            edge_used[(current, neighbor)] = edge
            queue.append(neighbor)

    unreachable = tables - visited
    if unreachable:
        raise DdlGenerationError(
            f"tables not reachable via the configured join graph: {sorted(unreachable)}"
        )
    return order, edge_used


def _select_list(legacy_columns: list[dict], column_mappings: list[dict]) -> list[str]:
    mapping_by_column = {m["legacy_column"]: m for m in column_mappings}
    select_items = []
    for legacy_col in legacy_columns:
        legacy_column = legacy_col["name"]
        mapping = mapping_by_column.get(legacy_column)
        if mapping is None:
            raise DdlGenerationError(f"legacy column '{legacy_column}' has no mapping entry")

        status = mapping.get("column_status") or "Mapped"
        if status not in VALID_COLUMN_STATUSES:
            raise DdlGenerationError(
                f"legacy column '{legacy_column}' has unknown column_status '{status}'; "
                f"must be one of {VALID_COLUMN_STATUSES}"
            )

        if status == "Retired":
            # Ignore whatever source is configured — a retired column is never read
            # from the new schema, but the view still owes its declared shape/type.
            expr = "NULL"
        else:
            source_table = mapping.get("source_table")
            expr = mapping["source_column_or_expression"]
            if source_table:
                expr = f"{_alias_for(source_table)}.{expr}"

        target_type = cast_type(legacy_col["type"])
        select_items.append(f"CAST({expr} AS {target_type}) AS [{legacy_column}]")
    return select_items


def build_select_sql(
    *, legacy_columns: list[dict], join_graph: list[dict], column_mappings: list[dict]
) -> str:
    """The plain `SELECT ...` body (no `CREATE VIEW` wrapper) — used both to build the
    deployed view's definition and, wrapped in a capped `SELECT TOP` by the caller, for
    a zero-DDL preview query (Constitution Principle I).

    `legacy_columns` is the legacy shape's captured column list — a list of
    `{name, type, nullable}` dicts (data-model.md §legacy_shape_capture) — `type` drives
    the CAST target for that column (see module docstring).
    """
    # An ordered (not just a set of) table list: insertion order follows the legacy
    # column order first, then the join graph — so the BFS root below is always the
    # first table a human would expect (the table backing the first legacy column),
    # making the generated FROM/JOIN order deterministic rather than dependent on
    # Python's arbitrary set iteration order.
    tables: dict[str, None] = {}
    mapping_by_column = {m["legacy_column"]: m for m in column_mappings}

    def _is_live_source(mapping: dict | None) -> bool:
        if mapping is None or not mapping.get("source_table"):
            return False
        return (mapping.get("column_status") or "Mapped") != "Retired"

    for legacy_col in legacy_columns:
        mapping = mapping_by_column.get(legacy_col["name"])
        if _is_live_source(mapping):
            tables.setdefault(mapping["source_table"], None)
    for mapping in column_mappings:
        if _is_live_source(mapping):
            tables.setdefault(mapping["source_table"], None)
    for edge in join_graph:
        tables.setdefault(edge["left_table"], None)
        tables.setdefault(edge["right_table"], None)

    if not tables:
        raise DdlGenerationError("no source tables referenced by column_mappings/join_graph")

    order, edge_used = _build_join_order(set(tables), join_graph, root=next(iter(tables)))

    select_items = _select_list(legacy_columns, column_mappings)

    root = order[0]
    from_clause = [f"FROM {root} AS {_alias_for(root)}"]
    for i in range(1, len(order)):
        table = order[i]
        # Find the edge that connected `table` into the visited set — it was
        # recorded keyed by (parent, table) during BFS.
        edge = None
        for j in range(i):
            candidate = edge_used.get((order[j], table))
            if candidate is not None:
                edge = candidate
                break
        if edge is None:  # pragma: no cover - defensive; _build_join_order guarantees this
            raise DdlGenerationError(f"no join edge found connecting '{table}' into the graph")
        join_type = edge.get("join_type", "inner")
        if join_type not in VALID_JOIN_TYPES:
            raise DdlGenerationError(f"unknown join_type '{join_type}'")
        sql_join = "LEFT JOIN" if join_type == "left" else "JOIN"
        left_alias = _alias_for(edge["left_table"])
        right_alias = _alias_for(edge["right_table"])
        from_clause.append(
            f"{sql_join} {table} AS {_alias_for(table)} "
            f"ON {left_alias}.{edge['left_column']} = {right_alias}.{edge['right_column']}"
        )

    select_sql = "SELECT\n    " + ",\n    ".join(select_items) + "\n" + "\n".join(from_clause)
    return select_sql


def build_create_view_sql(
    *,
    view_name: str,
    legacy_columns: list[dict],
    join_graph: list[dict],
    column_mappings: list[dict],
) -> str:
    """The exact `CREATE OR ALTER VIEW` statement stored verbatim as
    `view_definition_version.generated_sql` (FR-006/FR-008)."""
    select_sql = build_select_sql(
        legacy_columns=legacy_columns, join_graph=join_graph, column_mappings=column_mappings
    )
    return f"CREATE OR ALTER VIEW {view_name} AS\n{select_sql};"
