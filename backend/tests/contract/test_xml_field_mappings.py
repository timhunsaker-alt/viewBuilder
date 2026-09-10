"""Contract test (T044): `POST /xml-field-mappings/{id}/lookup` returns
`mapping_invalid` when no `field_paths` entry exists yet for the requested
`legacy_column` (FR-011, contracts/api.md). `find_field_path` is checked before any
database connection is opened (test_xml_lookup_service.py's
`test_lookup_raises_before_touching_the_connection_when_column_not_configured`), so
this contract test is fully runnable without a live MS SQL Server — the mapping's
`xml_connection_id` here points at `sample_connection`, which is never actually
reached.
"""

import uuid

from tests.conftest import requires_postgres


@requires_postgres
def test_lookup_rejects_a_column_with_no_configured_field_path(
    client, sample_connection, sample_legacy_shape
):
    created = client.post(
        "/api/v1/xml-field-mappings",
        json={
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "xml_connection_id": str(sample_connection.id),
            "xml_table_name": "dbo.legacy_application_xml",
            "xml_identity_column": "application_id",
            "xml_payload_column": "xml_payload",
            "field_paths": [
                {
                    "legacy_column": "collateral_value_cents",
                    "xpath": "(/Application/CollateralValue)[1]",
                    "cast_type": "BIGINT",
                }
            ],
        },
    ).json()

    response = client.post(
        f"/api/v1/xml-field-mappings/{created['id']}/lookup",
        json={"identity": "1", "legacy_column": "underwriting_score"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mapping_invalid"


@requires_postgres
def test_create_xml_field_mapping_and_add_a_version(client, sample_connection, sample_legacy_shape):
    created = client.post(
        "/api/v1/xml-field-mappings",
        json={
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "xml_connection_id": str(sample_connection.id),
            "xml_table_name": "dbo.legacy_application_xml",
            "xml_identity_column": "application_id",
            "xml_payload_column": "xml_payload",
            "field_paths": [],
        },
    )
    assert created.status_code == 201
    mapping_id = created.json()["id"]

    # US4 AC4: adding a field_paths entry for a newly-investigated column is a new
    # version, not a mutation of the (empty) first one.
    versioned = client.post(
        f"/api/v1/xml-field-mappings/{mapping_id}/versions",
        json={
            "field_paths": [
                {
                    "legacy_column": "underwriting_score",
                    "xpath": "(/Application/UnderwritingScore)[1]",
                    "cast_type": "INT",
                }
            ]
        },
    )
    assert versioned.status_code == 201
    assert versioned.json()["version_number"] == 2


@requires_postgres
def test_lookup_rejects_unknown_mapping(client):
    response = client.post(
        f"/api/v1/xml-field-mappings/{uuid.uuid4()}/lookup",
        json={"identity": "1", "legacy_column": "underwriting_score"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
