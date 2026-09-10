"""Unit tests (T014): `ddl_generator` produces a `CREATE OR ALTER VIEW` whose column
list/order exactly matches a given legacy shape's captured column order, for both a
star join (one central table joined to several others) and a chain join. No database
connection is required — this is pure SQL text assembly (FR-006).
"""

import pytest

from src.services.ddl_generator import DdlGenerationError, build_create_view_sql, build_select_sql


def test_star_join_preserves_legacy_column_order():
    legacy_columns = ["application_id", "first_name", "collateral_value_cents", "decision"]
    join_graph = [
        {
            "left_table": "dbo.loan_application",
            "left_column": "application_id",
            "right_table": "dbo.loan_applicant",
            "right_column": "application_id",
            "join_type": "inner",
        },
        {
            "left_table": "dbo.loan_application",
            "left_column": "application_id",
            "right_table": "dbo.loan_collateral",
            "right_column": "application_id",
            "join_type": "left",
        },
        {
            "left_table": "dbo.loan_application",
            "left_column": "application_id",
            "right_table": "dbo.loan_underwriting",
            "right_column": "application_id",
            "join_type": "inner",
        },
    ]
    column_mappings = [
        {
            "legacy_column": "application_id",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "application_id",
        },
        {
            "legacy_column": "first_name",
            "source_table": "dbo.loan_applicant",
            "source_column_or_expression": "first_name",
        },
        {
            "legacy_column": "collateral_value_cents",
            "source_table": "dbo.loan_collateral",
            "source_column_or_expression": "value_cents",
        },
        {
            "legacy_column": "decision",
            "source_table": "dbo.loan_underwriting",
            "source_column_or_expression": "decision",
        },
    ]

    sql = build_create_view_sql(
        view_name="dbo.compat_loan_application",
        legacy_columns=legacy_columns,
        join_graph=join_graph,
        column_mappings=column_mappings,
    )

    assert sql.startswith("CREATE OR ALTER VIEW dbo.compat_loan_application AS\n")
    # Column order in the SELECT list must exactly match legacy_columns order.
    select_lines = []
    for line in sql.split("SELECT\n", 1)[1].split("\n"):
        if line.startswith("FROM "):
            break
        select_lines.append(line)
    select_order = [
        line.strip().split(" AS ")[1].rstrip(",") for line in select_lines if " AS " in line
    ]
    assert select_order == [f"[{c}]" for c in legacy_columns]

    assert "loan_application AS loan_application" in sql
    assert (
        "JOIN dbo.loan_applicant AS loan_applicant "
        "ON loan_application.application_id = loan_applicant.application_id"
    ) in sql
    assert "LEFT JOIN dbo.loan_collateral AS loan_collateral" in sql
    assert "loan_underwriting.decision" in sql


def test_chain_join_reaches_every_table_in_order():
    legacy_columns = ["a_id", "b_val", "c_val"]
    join_graph = [
        {
            "left_table": "dbo.table_a",
            "left_column": "id",
            "right_table": "dbo.table_b",
            "right_column": "a_id",
            "join_type": "inner",
        },
        {
            "left_table": "dbo.table_b",
            "left_column": "id",
            "right_table": "dbo.table_c",
            "right_column": "b_id",
            "join_type": "inner",
        },
    ]
    column_mappings = [
        {
            "legacy_column": "a_id",
            "source_table": "dbo.table_a",
            "source_column_or_expression": "id",
        },
        {
            "legacy_column": "b_val",
            "source_table": "dbo.table_b",
            "source_column_or_expression": "val",
        },
        {
            "legacy_column": "c_val",
            "source_table": "dbo.table_c",
            "source_column_or_expression": "val",
        },
    ]

    sql = build_select_sql(
        legacy_columns=legacy_columns, join_graph=join_graph, column_mappings=column_mappings
    )
    assert "FROM dbo.table_a AS table_a" in sql
    assert "JOIN dbo.table_b AS table_b ON table_a.id = table_b.a_id" in sql
    assert "JOIN dbo.table_c AS table_c ON table_b.id = table_c.b_id" in sql


def test_single_table_needs_no_joins():
    legacy_columns = ["id", "name"]
    column_mappings = [
        {
            "legacy_column": "id",
            "source_table": "dbo.only_table",
            "source_column_or_expression": "id",
        },
        {
            "legacy_column": "name",
            "source_table": "dbo.only_table",
            "source_column_or_expression": "name",
        },
    ]
    sql = build_select_sql(
        legacy_columns=legacy_columns, join_graph=[], column_mappings=column_mappings
    )
    assert "FROM dbo.only_table AS only_table" in sql
    assert "JOIN" not in sql.replace("FROM dbo.only_table AS only_table", "")


def test_raw_expression_without_source_table_is_used_verbatim():
    legacy_columns = ["full_name"]
    column_mappings = [
        {
            "legacy_column": "full_name",
            "source_table": None,
            "source_column_or_expression": (
                "loan_applicant.first_name + ' ' + loan_applicant.last_name"
            ),
        },
        # a second mapping only to give us a FROM table to anchor on
    ]
    # Raw-expression-only mappings still need at least one table referenced via
    # join_graph or another mapping's source_table to anchor the FROM clause.
    join_graph = []
    column_mappings.append(
        {
            "legacy_column": "__anchor__",
            "source_table": "dbo.loan_applicant",
            "source_column_or_expression": "application_id",
        }
    )
    legacy_columns = ["full_name", "__anchor__"]

    sql = build_select_sql(
        legacy_columns=legacy_columns, join_graph=join_graph, column_mappings=column_mappings
    )
    assert ("loan_applicant.first_name + ' ' + loan_applicant.last_name AS [full_name]") in sql


def test_missing_mapping_for_a_legacy_column_raises():
    with pytest.raises(DdlGenerationError):
        build_select_sql(
            legacy_columns=["a", "b"],
            join_graph=[],
            column_mappings=[
                {"legacy_column": "a", "source_table": "dbo.t", "source_column_or_expression": "a"}
            ],
        )


def test_unreachable_table_raises():
    legacy_columns = ["a", "b"]
    column_mappings = [
        {"legacy_column": "a", "source_table": "dbo.t1", "source_column_or_expression": "a"},
        {"legacy_column": "b", "source_table": "dbo.t2", "source_column_or_expression": "b"},
    ]
    with pytest.raises(DdlGenerationError):
        build_select_sql(
            legacy_columns=legacy_columns, join_graph=[], column_mappings=column_mappings
        )
