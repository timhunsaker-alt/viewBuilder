"""Unit tests (T036/T037): reconciliation comparison logic correctly computes
matched/old-only/view-only counts and per-column mismatch detail from two given row
sets (FR-009), and row inflation (a join producing >1 view row per old-table
identity) is flagged distinctly from an ordinary mismatch (FR-014). Pure logic, no
database connection required.
"""

from src.services.reconciliation_engine import compare_row_sets

COMPARE_COLUMNS = ["application_id", "status", "loan_amount_cents"]


def test_all_rows_match_reports_zero_discrepancies():
    old_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 2, "status": "Closed", "loan_amount_cents": 200},
    ]
    view_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 2, "status": "Closed", "loan_amount_cents": 200},
    ]
    result = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column="application_id",
        compare_columns=COMPARE_COLUMNS,
    )
    assert result.rows_matched == 2
    assert result.rows_old_only == 0
    assert result.rows_view_only == 0
    assert result.rows_with_column_mismatch == 0
    assert result.row_inflation_flagged is False
    assert result.discrepancy_detail == []


def test_old_only_and_view_only_rows_are_counted_and_detailed():
    old_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 2, "status": "Closed", "loan_amount_cents": 200},
    ]
    view_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 3, "status": "Funded", "loan_amount_cents": 300},
    ]
    result = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column="application_id",
        compare_columns=COMPARE_COLUMNS,
    )
    assert result.rows_matched == 1
    assert result.rows_old_only == 1
    assert result.rows_view_only == 1
    identities_in_detail = {d["identity"] for d in result.discrepancy_detail}
    assert identities_in_detail == {2, 3}


def test_column_mismatch_is_counted_once_per_row_with_per_column_detail():
    old_rows = [{"application_id": 1, "status": "Funded", "loan_amount_cents": 100}]
    view_rows = [{"application_id": 1, "status": "Closed", "loan_amount_cents": 999}]
    result = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column="application_id",
        compare_columns=COMPARE_COLUMNS,
    )
    assert result.rows_matched == 0
    assert result.rows_with_column_mismatch == 1
    mismatched_columns = {d["column"] for d in result.discrepancy_detail}
    assert mismatched_columns == {"status", "loan_amount_cents"}
    status_detail = next(d for d in result.discrepancy_detail if d["column"] == "status")
    assert status_detail["old_value"] == "Funded"
    assert status_detail["view_value"] == "Closed"


def test_row_inflation_is_flagged_distinctly_from_an_ordinary_mismatch():
    old_rows = [{"application_id": 1, "status": "Funded", "loan_amount_cents": 100}]
    # A one-to-many join produced two view rows for the same old-table identity.
    view_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
    ]
    result = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column="application_id",
        compare_columns=COMPARE_COLUMNS,
    )
    assert result.row_inflation_flagged is True
    # Excluded from ordinary tallies — inflation is a structural problem, not a value
    # mismatch, even though every column's value happens to be identical.
    assert result.rows_matched == 0
    assert result.rows_with_column_mismatch == 0
    inflation_entries = [
        d for d in result.discrepancy_detail if "row inflation" in str(d["view_value"])
    ]
    assert len(inflation_entries) == 1
    assert inflation_entries[0]["identity"] == 1


def test_row_inflation_alongside_an_unrelated_clean_row():
    old_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 2, "status": "Closed", "loan_amount_cents": 200},
    ]
    view_rows = [
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 1, "status": "Funded", "loan_amount_cents": 100},
        {"application_id": 2, "status": "Closed", "loan_amount_cents": 200},
    ]
    result = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column="application_id",
        compare_columns=COMPARE_COLUMNS,
    )
    assert result.row_inflation_flagged is True
    assert result.rows_matched == 1  # application_id=2 is unaffected and clean
    assert result.rows_with_column_mismatch == 0
