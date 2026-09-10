"""Unit test (T032): `compute_column_diff` correctly identifies added/removed/
reordered columns between two versions' column lists (US2 AC3). Pure function, no
database connection needed.
"""

from src.services.view_definition_service import compute_column_diff


def test_no_change_reports_all_empty():
    columns = ["application_id", "applicant_first_name", "underwriting_decision"]
    diff = compute_column_diff(columns, columns)
    assert diff == {"added": [], "removed": [], "reordered": []}


def test_added_column_is_reported():
    previous = ["application_id", "applicant_first_name"]
    new = ["application_id", "applicant_first_name", "applicant_last_name"]
    diff = compute_column_diff(previous, new)
    assert diff["added"] == ["applicant_last_name"]
    assert diff["removed"] == []
    assert diff["reordered"] == []


def test_removed_column_is_reported():
    previous = ["application_id", "applicant_first_name", "underwriting_decision"]
    new = ["application_id", "applicant_first_name"]
    diff = compute_column_diff(previous, new)
    assert diff["added"] == []
    assert diff["removed"] == ["underwriting_decision"]
    assert diff["reordered"] == []


def test_reordered_columns_are_reported_in_new_order():
    previous = ["application_id", "applicant_first_name", "underwriting_decision"]
    new = ["application_id", "underwriting_decision", "applicant_first_name"]
    diff = compute_column_diff(previous, new)
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["reordered"] == ["application_id", "underwriting_decision", "applicant_first_name"]


def test_added_removed_and_reordered_can_all_occur_together():
    previous = ["a", "b", "c"]
    new = ["c", "b", "d"]
    diff = compute_column_diff(previous, new)
    assert diff["added"] == ["d"]
    assert diff["removed"] == ["a"]
    assert diff["reordered"] == ["c", "b"]
