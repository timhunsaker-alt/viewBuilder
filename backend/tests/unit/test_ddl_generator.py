"""Unit tests (T014 + follow-up): `ddl_generator` produces a `CREATE OR ALTER VIEW`
whose column list/order exactly matches a given legacy shape's captured column order,
for both a star join (one central table joined to several others) and a chain join,
casts every column to the legacy shape's own declared type (so the view always matches
the old table's types, not just its column names/order), and casts NULL (still in the
legacy column's own type) for any column marked `column_status="Retired"` rather than
reading a (possibly stale/absent) source. No database connection is required — this is
pure SQL text assembly (FR-006).
"""

import pytest

from src.services.ddl_generator import (
    DdlGenerationError,
    build_create_view_sql,
    build_select_sql,
    cast_type,
)


def _legacy_col(name: str, type_: str) -> dict:
    return {"name": name, "type": type_, "nullable": True}


def test_star_join_preserves_legacy_column_order_and_casts_every_column():
    legacy_columns = [
        _legacy_col("application_id", "INTEGER"),
        _legacy_col("first_name", 'NVARCHAR(100) COLLATE "SQL_Latin1_General_CP1_CI_AS"'),
        _legacy_col("collateral_value_cents", "BIGINT"),
        _legacy_col("decision", 'NVARCHAR(50) COLLATE "SQL_Latin1_General_CP1_CI_AS"'),
    ]
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
        line.strip().rsplit(" AS ", 1)[1].rstrip(",") for line in select_lines if " AS " in line
    ]
    assert select_order == [f"[{c['name']}]" for c in legacy_columns]

    # Every column is cast to its own legacy type, with any COLLATE clause stripped
    # (COLLATE is not valid syntax inside a CAST target).
    assert "CAST(loan_application.application_id AS INTEGER) AS [application_id]" in sql
    assert "CAST(loan_applicant.first_name AS NVARCHAR(100)) AS [first_name]" in sql
    assert "CAST(loan_collateral.value_cents AS BIGINT) AS [collateral_value_cents]" in sql
    assert "CAST(loan_underwriting.decision AS NVARCHAR(50)) AS [decision]" in sql

    assert "loan_application AS loan_application" in sql
    assert (
        "JOIN dbo.loan_applicant AS loan_applicant "
        "ON loan_application.application_id = loan_applicant.application_id"
    ) in sql
    assert "LEFT JOIN dbo.loan_collateral AS loan_collateral" in sql


def test_retired_column_casts_null_in_its_own_legacy_type_ignoring_any_source():
    legacy_columns = [
        _legacy_col("application_id", "INTEGER"),
        _legacy_col("legacy_only_field", 'NVARCHAR(50) COLLATE "SQL_Latin1_General_CP1_CI_AS"'),
    ]
    column_mappings = [
        {
            "legacy_column": "application_id",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "application_id",
        },
        {
            "legacy_column": "legacy_only_field",
            "column_status": "Retired",
            # A stale source left over from before this column was retired — must be
            # ignored entirely, not read, once column_status is Retired.
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "some_column_that_may_not_even_exist_anymore",
        },
    ]

    sql = build_select_sql(
        legacy_columns=legacy_columns, join_graph=[], column_mappings=column_mappings
    )

    assert "CAST(NULL AS NVARCHAR(50)) AS [legacy_only_field]" in sql
    assert "some_column_that_may_not_even_exist_anymore" not in sql
    # A retired column's (possibly-stale) source_table must not pull in a join/table
    # reference on its own — only loan_application (needed by the Mapped column) shows up.
    assert sql.count("FROM ") + sql.count("JOIN ") == 1


def test_unknown_column_status_raises():
    legacy_columns = [_legacy_col("a", "INTEGER")]
    column_mappings = [
        {
            "legacy_column": "a",
            "column_status": "Bogus",
            "source_table": "dbo.t",
            "source_column_or_expression": "a",
        }
    ]
    with pytest.raises(DdlGenerationError):
        build_select_sql(
            legacy_columns=legacy_columns, join_graph=[], column_mappings=column_mappings
        )


def test_cast_type_strips_collate_clause():
    assert cast_type('NVARCHAR(200) COLLATE "SQL_Latin1_General_CP1_CI_AS"') == "NVARCHAR(200)"
    assert cast_type("BIGINT") == "BIGINT"
    assert cast_type("DATE") == "DATE"


def test_chain_join_reaches_every_table_in_order():
    legacy_columns = [
        _legacy_col("a_id", "INTEGER"),
        _legacy_col("b_val", "INTEGER"),
        _legacy_col("c_val", "INTEGER"),
    ]
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
    legacy_columns = [_legacy_col("id", "INTEGER"), _legacy_col("name", "NVARCHAR(50)")]
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
    legacy_columns = [
        _legacy_col("full_name", "NVARCHAR(200)"),
        _legacy_col("__anchor__", "INTEGER"),
    ]
    column_mappings = [
        {
            "legacy_column": "full_name",
            "source_table": None,
            "source_column_or_expression": (
                "loan_applicant.first_name + ' ' + loan_applicant.last_name"
            ),
        },
        # a second mapping only to give us a FROM table to anchor on
        {
            "legacy_column": "__anchor__",
            "source_table": "dbo.loan_applicant",
            "source_column_or_expression": "application_id",
        },
    ]
    join_graph = []

    sql = build_select_sql(
        legacy_columns=legacy_columns, join_graph=join_graph, column_mappings=column_mappings
    )
    assert (
        "CAST(loan_applicant.first_name + ' ' + loan_applicant.last_name AS NVARCHAR(200)) "
        "AS [full_name]"
    ) in sql


def test_missing_mapping_for_a_legacy_column_raises():
    with pytest.raises(DdlGenerationError):
        build_select_sql(
            legacy_columns=[_legacy_col("a", "INTEGER"), _legacy_col("b", "INTEGER")],
            join_graph=[],
            column_mappings=[
                {"legacy_column": "a", "source_table": "dbo.t", "source_column_or_expression": "a"}
            ],
        )


def test_enum_coded_column_wraps_source_in_a_translation_case():
    legacy_columns = [
        _legacy_col("application_id", "INTEGER"),
        _legacy_col("status", "NVARCHAR(50)"),
    ]
    column_mappings = [
        {
            "legacy_column": "application_id",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "application_id",
        },
        {
            "legacy_column": "status",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "status_code",
            "enum_translation_version_id": "11111111-1111-1111-1111-111111111111",
        },
    ]
    enum_entries_by_version = {
        "11111111-1111-1111-1111-111111111111": [
            {"code": "1", "translated_value": "Funded"},
            {"code": "2", "translated_value": "Closed"},
        ]
    }

    sql = build_select_sql(
        legacy_columns=legacy_columns,
        join_graph=[],
        column_mappings=column_mappings,
        enum_entries_by_version=enum_entries_by_version,
    )

    assert (
        "CAST(CASE CAST(loan_application.status_code AS NVARCHAR(4000)) "
        "WHEN N'1' THEN N'Funded' WHEN N'2' THEN N'Closed' ELSE NULL END "
        "AS NVARCHAR(50)) AS [status]"
    ) in sql


def test_enum_coded_column_with_no_matching_version_entries_falls_back_to_null():
    legacy_columns = [_legacy_col("status", "NVARCHAR(50)")]
    column_mappings = [
        {
            "legacy_column": "status",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "status_code",
            "enum_translation_version_id": "does-not-exist",
        }
    ]
    sql = build_select_sql(
        legacy_columns=legacy_columns,
        join_graph=[],
        column_mappings=column_mappings,
        enum_entries_by_version={},
    )
    assert "CAST(NULL AS NVARCHAR(50)) AS [status]" in sql
    assert "CASE" not in sql


def test_enum_translation_entries_escape_embedded_single_quotes():
    legacy_columns = [_legacy_col("status", "NVARCHAR(50)")]
    column_mappings = [
        {
            "legacy_column": "status",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "status_code",
            "enum_translation_version_id": "v1",
        }
    ]
    sql = build_select_sql(
        legacy_columns=legacy_columns,
        join_graph=[],
        column_mappings=column_mappings,
        enum_entries_by_version={"v1": [{"code": "1", "translated_value": "Investor's Choice"}]},
    )
    assert "N'Investor''s Choice'" in sql


def test_retired_column_ignores_enum_translation_version_id_too():
    legacy_columns = [
        _legacy_col("application_id", "INTEGER"),
        _legacy_col("status", "NVARCHAR(50)"),
    ]
    column_mappings = [
        {
            "legacy_column": "application_id",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "application_id",
        },
        {
            "legacy_column": "status",
            "column_status": "Retired",
            "source_table": "dbo.loan_application",
            "source_column_or_expression": "status_code",
            "enum_translation_version_id": "v1",
        },
    ]
    sql = build_select_sql(
        legacy_columns=legacy_columns,
        join_graph=[],
        column_mappings=column_mappings,
        enum_entries_by_version={"v1": [{"code": "1", "translated_value": "Funded"}]},
    )
    assert "CAST(NULL AS NVARCHAR(50)) AS [status]" in sql
    assert "CASE" not in sql


def test_unreachable_table_raises():
    legacy_columns = [_legacy_col("a", "INTEGER"), _legacy_col("b", "INTEGER")]
    column_mappings = [
        {"legacy_column": "a", "source_table": "dbo.t1", "source_column_or_expression": "a"},
        {"legacy_column": "b", "source_table": "dbo.t2", "source_column_or_expression": "b"},
    ]
    with pytest.raises(DdlGenerationError):
        build_select_sql(
            legacy_columns=legacy_columns, join_graph=[], column_mappings=column_mappings
        )
