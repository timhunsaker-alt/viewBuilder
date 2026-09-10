"""Integration test (T045): all three XML lookup outcomes (found/field_missing/
document_not_found, FR-012) reproduced against the seeded mssql fixture's
`dbo.legacy_application_xml` table (backend/docker/mssql-init/seed.sql) — documents
exist for application_id 1-9, application_id 10 has none at all (document_not_found),
and application_id 5's document omits <CollateralValue> entirely (field_missing).
Skips cleanly when no live MS SQL Server / ODBC Driver 18 is reachable in this
sandbox, matching tests/integration/test_view_deploy_roundtrip.py's pattern.
"""

import uuid

import pytest
from sqlalchemy import text

from src.connectors.mssql import build_engine
from tests.conftest import requires_postgres

FIELD_PATHS = [
    {
        "legacy_column": "collateral_value_cents",
        "xpath": "(/Application/CollateralValue)[1]",
        "cast_type": "BIGINT",
    },
]


@requires_postgres
def test_all_three_outcomes_against_seeded_xml_documents(
    client, sample_connection, sample_legacy_shape
):
    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip", not "fail"
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    mapping = client.post(
        "/api/v1/xml-field-mappings",
        json={
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "xml_connection_id": str(sample_connection.id),
            "xml_table_name": "dbo.legacy_application_xml",
            "xml_identity_column": "application_id",
            "xml_payload_column": "xml_payload",
            "field_paths": FIELD_PATHS,
        },
    ).json()
    mapping_id = mapping["id"]

    # application_id=1 has a CollateralValue in its document -> found.
    found = client.post(
        f"/api/v1/xml-field-mappings/{mapping_id}/lookup",
        json={"identity": "1", "legacy_column": "collateral_value_cents"},
    )
    assert found.status_code == 200
    found_body = found.json()
    assert found_body["outcome"] == "found"
    assert found_body["value"] == "32000000"

    # application_id=5's document exists but omits <CollateralValue> -> field_missing.
    missing = client.post(
        f"/api/v1/xml-field-mappings/{mapping_id}/lookup",
        json={"identity": "5", "legacy_column": "collateral_value_cents"},
    )
    assert missing.status_code == 200
    missing_body = missing.json()
    assert missing_body["outcome"] == "field_missing"
    assert missing_body["value"] is None

    # application_id=10 has no XML document row at all -> document_not_found.
    not_found = client.post(
        f"/api/v1/xml-field-mappings/{mapping_id}/lookup",
        json={"identity": "10", "legacy_column": "collateral_value_cents"},
    )
    assert not_found.status_code == 200
    not_found_body = not_found.json()
    assert not_found_body["outcome"] == "document_not_found"
    assert not_found_body["value"] is None


@requires_postgres
def test_lookup_mapping_invalid_still_enforced_against_live_connection(
    client, sample_connection, sample_legacy_shape
):
    try:
        engine = build_engine(sample_connection)
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live MS SQL Server fixture not reachable in this environment: {exc}")

    mapping = client.post(
        "/api/v1/xml-field-mappings",
        json={
            "legacy_shape_capture_id": str(sample_legacy_shape.id),
            "xml_connection_id": str(sample_connection.id),
            "xml_table_name": "dbo.legacy_application_xml",
            "xml_identity_column": "application_id",
            "xml_payload_column": "xml_payload",
            "field_paths": FIELD_PATHS,
        },
    ).json()

    response = client.post(
        f"/api/v1/xml-field-mappings/{mapping['id']}/lookup",
        json={"identity": str(uuid.uuid4()), "legacy_column": "underwriting_score"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mapping_invalid"
