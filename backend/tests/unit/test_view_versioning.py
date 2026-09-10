"""Unit test (T030): editing and redeploying a view definition creates a new,
immutable `view_definition_version` row — an existing version is never mutated
(Constitution Principle II, FR-007). Exercises `ViewDefinitionService` directly
(not through the HTTP API) against the Postgres metadata store; no live MS SQL
Server connection is required since view-definition creation/versioning never opens
an external database connection (only preview/deploy do).
"""

import copy

from src.services.view_definition_service import ViewDefinitionService
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
    },
    {
        "legacy_column": "applicant_first_name",
        "source_table": "dbo.loan_applicant",
        "source_column_or_expression": "first_name",
    },
    {
        "legacy_column": "collateral_value_cents",
        "source_table": None,
        "source_column_or_expression": "NULL",
    },
    {
        "legacy_column": "underwriting_decision",
        "source_table": None,
        "source_column_or_expression": "NULL",
    },
]


@requires_postgres
def test_editing_and_saving_a_new_version_does_not_mutate_the_prior_version_row(
    db_session, sample_connection, sample_legacy_shape
):
    service = ViewDefinitionService(db_session)
    definition = service.create_view_definition(
        name="compat-versioning-unit-test",
        legacy_shape_capture_id=sample_legacy_shape.id,
        target_connection_id=sample_connection.id,
        join_graph=JOIN_GRAPH,
        column_mappings=COLUMN_MAPPINGS,
    )
    versions_before = service.list_versions(definition.id)
    assert len(versions_before) == 1
    v1 = versions_before[0]
    v1_id = v1.id
    v1_generated_sql_snapshot = v1.generated_sql
    v1_column_mappings_snapshot = copy.deepcopy(v1.column_mappings)

    edited_mappings = [dict(m) for m in COLUMN_MAPPINGS]
    edited_mappings[1]["source_column_or_expression"] = "last_name"  # was first_name

    v2 = service.save_new_version(
        view_definition_id=definition.id,
        join_graph=JOIN_GRAPH,
        column_mappings=edited_mappings,
    )
    assert v2.version_number == 2
    assert v2.id != v1_id

    # The row identified by v1's id, re-fetched fresh from the DB, must be byte-for-byte
    # unchanged — editing must never mutate it in place.
    db_session.expire_all()
    v1_reloaded = service.list_versions(definition.id)[0]
    assert v1_reloaded.id == v1_id
    assert v1_reloaded.version_number == 1
    assert v1_reloaded.generated_sql == v1_generated_sql_snapshot
    assert v1_reloaded.column_mappings == v1_column_mappings_snapshot
    assert "loan_applicant.first_name" in v1_reloaded.generated_sql

    versions_after = service.list_versions(definition.id)
    assert len(versions_after) == 2
    assert {v.version_number for v in versions_after} == {1, 2}

    # The definition's "current" pointer moves forward, but that's a pointer update on
    # view_definition, not a mutation of the immutable version row itself.
    db_session.refresh(definition)
    assert definition.current_version_id == v2.id
