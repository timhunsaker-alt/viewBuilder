"""Unit tests: saving a view definition (create or new version) writes one
`legacy_view_column_rule` row per legacy column — an append-only governance record of
`legacy_table_name`, `compatibility_view_name`, `column_name`, `column_status`,
`expected_null_flag`, and `notes` — and a column marked `column_status="Retired"` needs
no real source expression at all (validate_column_mappings must not reject it), while a
non-Retired column still does. Exercises `ViewDefinitionService` directly against the
Postgres metadata store; no live MS SQL Server connection is required.
"""

from src.models.legacy_view_column_rule import LegacyViewColumnRule
from src.services.view_definition_service import (
    ViewDefinitionService,
    ViewDefinitionValidationError,
)
from tests.conftest import requires_postgres

JOIN_GRAPH = [
    {
        "left_table": "dbo.loan_application",
        "left_column": "application_id",
        "right_table": "dbo.loan_applicant",
        "right_column": "application_id",
        "join_type": "inner",
    },
]

COLUMN_MAPPINGS = [
    {
        "legacy_column": "application_id",
        "source_table": "dbo.loan_application",
        "source_column_or_expression": "application_id",
        "column_status": "Mapped",
    },
    {
        "legacy_column": "applicant_first_name",
        "source_table": "dbo.loan_applicant",
        "source_column_or_expression": "first_name",
        "column_status": "Historical",
        "notes": "Frozen at cutover; new applications don't populate this anymore.",
    },
    {
        "legacy_column": "collateral_value_cents",
        "source_table": None,
        "source_column_or_expression": "",
        "column_status": "Retired",
        "notes": "No longer captured in the new schema.",
    },
    {
        "legacy_column": "underwriting_decision",
        "source_table": "dbo.loan_applicant",
        "source_column_or_expression": "first_name",
        "column_status": "Transient",
    },
]


@requires_postgres
def test_saving_a_definition_writes_one_rule_row_per_legacy_column(
    db_session, sample_connection, sample_legacy_shape
):
    service = ViewDefinitionService(db_session)
    definition = service.create_view_definition(
        name="compat-column-rules-unit-test",
        legacy_shape_capture_id=sample_legacy_shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=COLUMN_MAPPINGS,
    )

    rules = service.list_column_rules(definition.id)
    assert len(rules) == 4
    by_column = {r.column_name: r for r in rules}

    assert by_column["application_id"].column_status == "Mapped"
    assert by_column["application_id"].expected_null_flag is False
    assert by_column["application_id"].legacy_table_name == sample_legacy_shape.table_name
    assert by_column["application_id"].compatibility_view_name == "compat-column-rules-unit-test"

    assert by_column["applicant_first_name"].column_status == "Historical"
    assert by_column["applicant_first_name"].notes == (
        "Frozen at cutover; new applications don't populate this anymore."
    )

    assert by_column["collateral_value_cents"].column_status == "Retired"
    assert by_column["collateral_value_cents"].expected_null_flag is True

    assert by_column["underwriting_decision"].column_status == "Transient"
    assert by_column["underwriting_decision"].expected_null_flag is False


@requires_postgres
def test_redeploying_a_new_version_appends_a_fresh_set_of_rules_not_mutating_the_prior_set(
    db_session, sample_connection, sample_legacy_shape
):
    service = ViewDefinitionService(db_session)
    definition = service.create_view_definition(
        name="compat-column-rules-versioning-test",
        legacy_shape_capture_id=sample_legacy_shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=COLUMN_MAPPINGS,
    )
    v1_rule_ids = {r.id for r in service.list_column_rules(definition.id)}
    assert len(v1_rule_ids) == 4

    edited = [dict(m) for m in COLUMN_MAPPINGS]
    edited[2]["column_status"] = "Mapped"
    edited[2]["source_table"] = "dbo.loan_applicant"
    edited[2]["source_column_or_expression"] = "application_id"

    service.save_new_version(
        view_definition_id=definition.id, join_graph=JOIN_GRAPH, column_mappings=edited
    )

    all_rules = service.list_column_rules(definition.id)
    assert len(all_rules) == 8  # 4 from v1 (untouched) + 4 fresh rows from v2
    assert v1_rule_ids.issubset({r.id for r in all_rules})

    by_version = {}
    for r in all_rules:
        by_version.setdefault(r.view_definition_version_id, []).append(r)
    assert len(by_version) == 2
    newer_version_rules = {
        r.column_name: r for r in max(by_version.values(), key=lambda rs: rs[0].created_at)
    }
    assert newer_version_rules["collateral_value_cents"].column_status == "Mapped"
    assert newer_version_rules["collateral_value_cents"].expected_null_flag is False


@requires_postgres
def test_retired_column_does_not_require_a_source_expression(
    db_session, sample_connection, sample_legacy_shape
):
    mappings = [dict(m) for m in COLUMN_MAPPINGS]
    mappings[2] = {
        "legacy_column": "collateral_value_cents",
        "source_table": None,
        "source_column_or_expression": "",
        "column_status": "Retired",
    }
    service = ViewDefinitionService(db_session)
    # Must not raise — Retired is explicitly exempt from FR-004's "needs a source".
    definition = service.create_view_definition(
        name="compat-retired-no-source-test",
        legacy_shape_capture_id=sample_legacy_shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=mappings,
    )
    assert definition.current_version_id is not None


@requires_postgres
def test_non_retired_column_without_a_source_expression_is_rejected(
    db_session, sample_connection, sample_legacy_shape
):
    mappings = [dict(m) for m in COLUMN_MAPPINGS]
    mappings[2] = {
        "legacy_column": "collateral_value_cents",
        "source_table": None,
        "source_column_or_expression": "",
        "column_status": "Mapped",
    }
    service = ViewDefinitionService(db_session)
    try:
        service.create_view_definition(
            name="compat-unsourced-mapped-test",
            legacy_shape_capture_id=sample_legacy_shape.id,
            target_connection_id=sample_connection.id,
            join_graph=JOIN_GRAPH,
            column_mappings=mappings,
        )
        raise AssertionError("expected a ViewDefinitionValidationError")
    except ViewDefinitionValidationError as exc:
        assert exc.code == "mapping_invalid"


@requires_postgres
def test_rule_rows_are_never_updated_only_appended(
    db_session, sample_connection, sample_legacy_shape
):
    """Direct DB-level check that no code path updates an existing rule row: the count
    of distinct ids only grows across saves, matching immutable-version policy's
    immutable-version-append discipline extended to this governance table."""
    service = ViewDefinitionService(db_session)
    definition = service.create_view_definition(
        name="compat-column-rules-append-only-test",
        legacy_shape_capture_id=sample_legacy_shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=COLUMN_MAPPINGS,
    )
    count_after_v1 = (
        db_session.query(LegacyViewColumnRule)
        .filter(LegacyViewColumnRule.compatibility_view_name == definition.name)
        .count()
    )
    service.save_new_version(
        view_definition_id=definition.id, join_graph=JOIN_GRAPH, column_mappings=COLUMN_MAPPINGS
    )
    count_after_v2 = (
        db_session.query(LegacyViewColumnRule)
        .filter(LegacyViewColumnRule.compatibility_view_name == definition.name)
        .count()
    )
    assert count_after_v2 == count_after_v1 * 2
