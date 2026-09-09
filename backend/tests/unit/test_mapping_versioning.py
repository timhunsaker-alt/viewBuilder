"""Unit tests: mapping-version immutability (Constitution Principle II).

Editing a saved mapping MUST create a new mapping_version row and MUST NOT mutate an
existing one, even indirectly through the ORM session.
"""

import uuid

from src.models.mapping import MappingVersion
from src.services.mapping_service import MappingService
from tests.conftest import requires_postgres


@requires_postgres
def test_save_new_version_leaves_prior_version_row_untouched(db_session, sample_connection):
    service = MappingService(db_session)
    definition = service.create_mapping(
        name=f"m-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        source_table="dbo.legacy_customer",
        target_connection_id=sample_connection.id,
        target_table="dbo.target_customer",
        column_links=[{"sourceColumn": "email", "targetColumn": "email_address"}],
        row_identity_column="customer_id",
    )
    first_version_id = definition.current_version_id
    first_version_snapshot = db_session.get(MappingVersion, first_version_id).column_links

    service.save_new_version(
        mapping_definition_id=definition.id,
        column_links=[{"sourceColumn": "full_name", "targetColumn": "display_name"}],
    )

    # Re-fetch the original version row from the DB (not from the ORM identity map) to
    # prove it was never updated in place.
    db_session.expire_all()
    reloaded_first_version = db_session.get(MappingVersion, first_version_id)
    assert reloaded_first_version.column_links == first_version_snapshot
    assert reloaded_first_version.version_number == 1


@requires_postgres
def test_version_numbers_increment_monotonically_per_definition(db_session, sample_connection):
    service = MappingService(db_session)
    definition = service.create_mapping(
        name=f"m-{uuid.uuid4().hex[:8]}",
        kind="column_mapping",
        source_connection_id=sample_connection.id,
        source_table="dbo.legacy_customer",
        target_connection_id=sample_connection.id,
        target_table="dbo.target_customer",
        column_links=[],
        row_identity_column="customer_id",
    )
    v2 = service.save_new_version(mapping_definition_id=definition.id, column_links=[])
    v3 = service.save_new_version(mapping_definition_id=definition.id, column_links=[])
    assert v2.version_number == 2
    assert v3.version_number == 3
