"""``Feature.scaling``: a feature's one line that grows with the character's level (Song of Rest 1d6 -> 1d8 ...)."""

import pytest

SONG_OF_REST = {
    "label": "Доп. хиты",
    "steps": [
        {"level": 9, "value": "1к8"},
        {"level": 2, "value": "1к6"},
        {"level": 17, "value": "1к12"},
        {"level": 13, "value": "1к10"},
    ],
}
SORTED_STEPS = [
    {"level": 2, "value": "1к6"},
    {"level": 9, "value": "1к8"},
    {"level": 13, "value": "1к10"},
    {"level": 17, "value": "1к12"},
]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _create_song_of_rest(client, gm_token, class_id):
    response = await client.post(
        "/features",
        json={"name": "Песнь отдыха", "source_type": "CLASS", "class_id": class_id, "level": 2, "scaling": SONG_OF_REST},
        headers=_auth(gm_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureScaling:
    async def test_create_returns_sorted_steps(self, client, gm_token, create_class):
        bard = await create_class(name="Bard")

        created = await _create_song_of_rest(client, gm_token, bard.id)

        assert created["scaling"] == {"label": "Доп. хиты", "steps": SORTED_STEPS}
        detail = await client.get(f"/features/{created['id']}")
        assert detail.json()["scaling"] == {"label": "Доп. хиты", "steps": SORTED_STEPS}

    async def test_feature_without_scaling_reads_null(self, client, gm_token):
        response = await client.post(
            "/features", json={"name": "Lucky", "source_type": "OTHER"}, headers=_auth(gm_token)
        )

        assert response.status_code == 201
        assert response.json()["scaling"] is None

    async def test_patch_replaces_and_clears_scaling(self, client, gm_token, create_class):
        bard = await create_class(name="Bard")
        created = await _create_song_of_rest(client, gm_token, bard.id)

        replaced = await client.patch(
            f"/features/{created['id']}",
            json={"scaling": {"label": "Кость", "steps": [{"level": 5, "value": "к8"}]}},
            headers=_auth(gm_token),
        )
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["scaling"] == {"label": "Кость", "steps": [{"level": 5, "value": "к8"}]}

        cleared = await client.patch(f"/features/{created['id']}", json={"scaling": None}, headers=_auth(gm_token))
        assert cleared.status_code == 200
        assert cleared.json()["scaling"] is None

    async def test_duplicate_step_levels_are_rejected(self, client, gm_token, create_class):
        bard = await create_class(name="Bard")

        response = await client.post(
            "/features",
            json={
                "name": "Песнь отдыха",
                "source_type": "CLASS",
                "class_id": bard.id,
                "level": 2,
                "scaling": {"label": "Доп. хиты", "steps": [{"level": 2, "value": "1к6"}, {"level": 2, "value": "1к8"}]},
            },
            headers=_auth(gm_token),
        )

        assert response.status_code == 422

    async def test_nested_class_response_carries_scaling(self, client, gm_token, create_class):
        bard = await create_class(name="Bard")
        await _create_song_of_rest(client, gm_token, bard.id)

        response = await client.get(f"/classes/{bard.id}")

        assert response.status_code == 200
        features = response.json()["features"]
        assert [feature["scaling"] for feature in features] == [{"label": "Доп. хиты", "steps": SORTED_STEPS}]

    async def test_character_feature_brief_carries_scaling(self, client, gm, gm_token, create_class, create_character):
        bard = await create_class(name="Bard")
        character = await create_character(owner_id=gm.id, class_id=bard.id, level=10)
        await _create_song_of_rest(client, gm_token, bard.id)

        response = await client.get(f"/characters/{character.id}/features", headers=_auth(gm_token))

        assert response.status_code == 200
        [grant] = response.json()
        assert grant["feature"]["scaling"] == {"label": "Доп. хиты", "steps": SORTED_STEPS}
