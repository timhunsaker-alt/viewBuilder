from tests.conftest import requires_postgres


@requires_postgres
def test_create_mapping_creates_definition_and_first_version(client, sample_connection):
    response = client.post(
        "/api/v1/mappings",
        json={
            "name": "customer-mapping",
            "kind": "column_mapping",
            "source_connection_id": str(sample_connection.id),
            "source_table": "dbo.legacy_customer",
            "target_connection_id": str(sample_connection.id),
            "target_table": "dbo.target_customer",
            "column_links": [{"sourceColumn": "full_name", "targetColumn": "display_name"}],
            "row_identity_column": "customer_id",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "customer-mapping"
    assert body["current_version_id"] is not None

    versions = client.get(f"/api/v1/mappings/{body['id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["column_links"] == [
        {"sourceColumn": "full_name", "targetColumn": "display_name"}
    ]


@requires_postgres
def test_post_new_version_does_not_mutate_prior_version(client, sample_connection):
    create = client.post(
        "/api/v1/mappings",
        json={
            "name": "account-mapping",
            "kind": "column_mapping",
            "source_connection_id": str(sample_connection.id),
            "source_table": "dbo.legacy_account",
            "target_connection_id": str(sample_connection.id),
            "target_table": "dbo.target_account",
            "column_links": [{"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}],
            "row_identity_column": "account_id",
        },
    ).json()
    mapping_id = create["id"]

    updated = client.post(
        f"/api/v1/mappings/{mapping_id}/versions",
        json={
            "column_links": [
                {"sourceColumn": "balance_cents", "targetColumn": "balance_cents"},
                {"sourceColumn": "customer_id", "targetColumn": "customer_id"},
            ]
        },
    )
    assert updated.status_code == 201
    assert updated.json()["version_number"] == 2

    versions = client.get(f"/api/v1/mappings/{mapping_id}/versions").json()
    assert len(versions) == 2
    v1 = next(v for v in versions if v["version_number"] == 1)
    assert v1["column_links"] == [
        {"sourceColumn": "balance_cents", "targetColumn": "balance_cents"}
    ]
