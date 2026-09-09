from tests.conftest import requires_postgres


@requires_postgres
def test_create_enum_translation_creates_table_and_first_version(client):
    response = client.post(
        "/api/v1/enum-translations",
        json={
            "name": "legacy-retirement-reason-codes",
            "entries": [
                {"code": "1", "translated_value": "Voluntary"},
                {"code": "2", "translated_value": "Involuntary"},
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "legacy-retirement-reason-codes"
    assert body["current_version_id"] is not None


@requires_postgres
def test_create_enum_translation_rejects_duplicate_codes(client):
    response = client.post(
        "/api/v1/enum-translations",
        json={
            "name": "duplicate-code-table",
            "entries": [
                {"code": "1", "translated_value": "A"},
                {"code": "1", "translated_value": "B"},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "enum_translation_invalid"


@requires_postgres
def test_post_new_version_does_not_mutate_prior_version(client):
    created = client.post(
        "/api/v1/enum-translations",
        json={"name": "status-codes", "entries": [{"code": "0", "translated_value": "Active"}]},
    ).json()

    updated = client.post(
        f"/api/v1/enum-translations/{created['id']}/versions",
        json={
            "entries": [
                {"code": "0", "translated_value": "Active"},
                {"code": "1", "translated_value": "Retired"},
            ]
        },
    )
    assert updated.status_code == 201
    assert updated.json()["version_number"] == 2
    assert len(updated.json()["entries"]) == 2
