"""Unit test (T015): join-graph reachability validation rejects an orphan table
(FR-002) — no database connection required.
"""

import pytest

from src.services.view_definition_service import (
    ViewDefinitionValidationError,
    validate_join_graph,
)


def test_fully_connected_star_graph_is_valid():
    tables = {"dbo.a", "dbo.b", "dbo.c"}
    join_graph = [
        {
            "left_table": "dbo.a",
            "left_column": "id",
            "right_table": "dbo.b",
            "right_column": "a_id",
        },
        {
            "left_table": "dbo.a",
            "left_column": "id",
            "right_table": "dbo.c",
            "right_column": "a_id",
        },
    ]
    validate_join_graph(tables, join_graph)  # must not raise


def test_orphan_table_is_rejected():
    tables = {"dbo.a", "dbo.b", "dbo.orphan"}
    join_graph = [
        {
            "left_table": "dbo.a",
            "left_column": "id",
            "right_table": "dbo.b",
            "right_column": "a_id",
        },
    ]
    with pytest.raises(ViewDefinitionValidationError) as exc_info:
        validate_join_graph(tables, join_graph)
    assert exc_info.value.code == "mapping_invalid"
    assert "dbo.orphan" in str(exc_info.value)


def test_single_table_needs_no_join_graph():
    validate_join_graph({"dbo.only_table"}, [])  # must not raise


def test_empty_tables_is_valid():
    validate_join_graph(set(), [])  # must not raise
