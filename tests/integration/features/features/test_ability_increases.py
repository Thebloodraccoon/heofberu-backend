"""Tests for the feature ability-increase endpoints (fixed stat effects)."""

import pytest


async def set_increases(client, gm_token, feature_id, increases):
    return await client.put(
        f"/features/{feature_id}/ability-increases",
        json={"ability_increases": increases},
        headers={"Authorization": f"Bearer {gm_token}"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureAbilityIncreasesCrud:
    async def test_empty_by_default(self, client, gm_token, create_feature):
        feature = await create_feature(name="Plain Feature")

        response = await client.get(
            f"/features/{feature.id}/ability-increases",
        )

        assert response.status_code == 200
        assert response.json() == {"feature_id": feature.id, "ability_increases": []}

    async def test_gm_can_set_effects(self, client, gm_token, create_feature):
        feature = await create_feature(name="Primal Champion")

        response = await set_increases(
            client,
            gm_token,
            feature.id,
            [
                {"ability": "STR", "amount": 4, "new_cap": 24},
                {"ability": "CON", "amount": 4, "new_cap": None},
            ],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["feature_id"] == feature.id
        assert {item["ability"]: item["amount"] for item in body["ability_increases"]} == {"STR": 4, "CON": 4}
        assert body["ability_increases"][0]["new_cap"] == 24

    async def test_set_is_a_full_replace(self, client, gm_token, create_feature):
        feature = await create_feature(name="Shifting Effect")
        await set_increases(
            client,
            gm_token,
            feature.id,
            [{"ability": "STR", "amount": 2}, {"ability": "DEX", "amount": 1}],
        )

        response = await set_increases(client, gm_token, feature.id, [{"ability": "CHA", "amount": -2}])

        assert response.status_code == 200
        abilities = {item["ability"] for item in response.json()["ability_increases"]}
        assert abilities == {"CHA"}

    async def test_clear_with_empty_list(self, client, gm_token, create_feature):
        feature = await create_feature(name="Temporary Effect")
        await set_increases(client, gm_token, feature.id, [{"ability": "WIS", "amount": 1}])

        response = await set_increases(client, gm_token, feature.id, [])

        assert response.status_code == 200
        assert response.json()["ability_increases"] == []

    async def test_duplicate_ability_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Dup Effect")

        response = await set_increases(
            client,
            gm_token,
            feature.id,
            [{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 1}],
        )

        assert response.status_code == 422

    async def test_unknown_feature_returns_404(self, client, gm_token):
        response = await set_increases(client, gm_token, 999999, [])

        assert response.status_code == 404

    async def test_player_cannot_write(self, client, player_token, create_feature):
        feature = await create_feature(name="Player Proof")

        response = await set_increases(client, player_token, feature.id, [{"ability": "STR", "amount": 1}])

        assert response.status_code == 403

    async def test_read_is_open(self, client, create_feature):
        feature = await create_feature(name="Open Read")

        response = await client.get(f"/features/{feature.id}/ability-increases")

        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureResponsesEmbedAbilityIncreases:
    async def test_feature_detail_response_embeds_ability_increases(self, client, gm_token, create_feature):
        feature = await create_feature(name="Primal Champion")
        await set_increases(
            client,
            gm_token,
            feature.id,
            [{"ability": "STR", "amount": 4, "new_cap": 30}],
        )

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["ability_increases"] == [{"ability": "STR", "amount": 4, "new_cap": 30}]

    async def test_race_feature_list_embeds_ability_increases(self, client, gm_token, create_race, create_feature):
        race = await create_race(name="Half-Orc")
        feature = await create_feature(name="Savage Attacks", source_type="RACE", race_id=race.id)
        await set_increases(
            client,
            gm_token,
            feature.id,
            [{"ability": "STR", "amount": 2, "new_cap": 30}],
        )

        response = await client.get(f"/races/{race.id}/features")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["name"] == "Savage Attacks"
        assert body[0]["ability_increases"] == [{"ability": "STR", "amount": 2, "new_cap": 30}]

    async def test_fresh_feature_embeds_empty_ability_increases(self, client, create_feature):
        feature = await create_feature(name="Plain")

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        assert response.json()["ability_increases"] == []
