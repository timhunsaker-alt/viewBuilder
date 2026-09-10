"""Keyed row/column comparison between a deployed view's live output and its
`legacy_shape_capture`'s old table (FR-009/FR-014, research.md §2).

Pure comparison logic: callers fetch both sides' rows (each already `ORDER BY` the
identity column at the SQL layer, per research.md §2's chunk-friendly streaming
design) and pass them in here as row dicts — this module never opens a database
connection itself, so it is fully unit-testable against contrived row sets.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

# Caps how many discrepancy_detail entries accumulate per run so a badly-mismatched
# large table doesn't produce an unbounded JSONB payload — still "enough to
# investigate specific discrepancies" (US3 AC2), just not an exhaustive dump.
DISCREPANCY_DETAIL_CAP = 500


@dataclass
class ReconciliationResult:
    rows_matched: int = 0
    rows_old_only: int = 0
    rows_view_only: int = 0
    rows_with_column_mismatch: int = 0
    row_inflation_flagged: bool = False
    discrepancy_detail: list[dict] = field(default_factory=list)


def _group_by_identity(rows: Iterable[dict], identity_column: str) -> dict[object, list[dict]]:
    grouped: dict[object, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row[identity_column], []).append(row)
    return grouped


def _append_detail(result: ReconciliationResult, entry: dict) -> None:
    if len(result.discrepancy_detail) < DISCREPANCY_DETAIL_CAP:
        result.discrepancy_detail.append(entry)


def compare_row_sets(
    *,
    old_rows: Iterable[dict],
    view_rows: Iterable[dict],
    identity_column: str,
    compare_columns: list[str],
) -> ReconciliationResult:
    """FR-009: for the identity column's current population, report how many rows
    match exactly, how many exist only on one side, and how many exist on both but
    with at least one differing column — plus per-row/column detail (US3 AC1/AC2).

    FR-014: when the view produces more than one row per old-table identity, that
    identity is flagged via `row_inflation_flagged` and recorded in
    `discrepancy_detail` distinctly from an ordinary value mismatch — it is
    deliberately excluded from `rows_matched`/`rows_with_column_mismatch` so those
    counts stay meaningful (a structural join problem is not the same claim as "this
    row's data differs").
    """
    old_by_id = _group_by_identity(old_rows, identity_column)
    view_by_id = _group_by_identity(view_rows, identity_column)

    old_ids = set(old_by_id)
    view_ids = set(view_by_id)

    result = ReconciliationResult()
    result.rows_old_only = len(old_ids - view_ids)
    result.rows_view_only = len(view_ids - old_ids)

    for identity in sorted(old_ids - view_ids, key=str):
        _append_detail(
            result,
            {
                "identity": identity,
                "column": None,
                "old_value": "<present>",
                "view_value": "<missing: old-only row>",
            },
        )
    for identity in sorted(view_ids - old_ids, key=str):
        _append_detail(
            result,
            {
                "identity": identity,
                "column": None,
                "old_value": "<missing: view-only row>",
                "view_value": "<present>",
            },
        )

    for identity in sorted(old_ids & view_ids, key=str):
        view_rows_for_id = view_by_id[identity]
        if len(view_rows_for_id) > 1:
            result.row_inflation_flagged = True
            _append_detail(
                result,
                {
                    "identity": identity,
                    "column": None,
                    "old_value": "1 row",
                    "view_value": f"{len(view_rows_for_id)} rows (row inflation, FR-014)",
                },
            )
            continue

        old_row = old_by_id[identity][0]
        view_row = view_rows_for_id[0]
        row_mismatched = False
        for column in compare_columns:
            old_value = old_row.get(column)
            view_value = view_row.get(column)
            if old_value != view_value:
                row_mismatched = True
                _append_detail(
                    result,
                    {
                        "identity": identity,
                        "column": column,
                        "old_value": old_value,
                        "view_value": view_value,
                    },
                )
        if row_mismatched:
            result.rows_with_column_mismatch += 1
        else:
            result.rows_matched += 1

    return result
