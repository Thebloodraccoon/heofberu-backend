"""Tests for the subrace endpoints: CRUD, ability bonuses, and nested features."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceCrud:
    async def test_player_cannot_create_subrace(self, client, player_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post(
            "/races/subraces",
            params={"race_id": race.id},
            json={"name": "High Elf"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_subrace(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post(
            "/races/subraces",
            params={"race_id": race.id},
            json={"name": "High Elf", "description": "Graceful and keen-eyed."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "High Elf"
        assert body["race_id"] == race.id
        assert body["ability_bonuses"] == []

    async def test_gm_can_create_subrace_with_ability_bonuses_and_features(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post(
            "/races/subraces",
            params={"race_id": race.id},
            json={
                "name": "High Elf",
                "ability_bonuses": [{"ability": "INT", "bonus": 1}],
                "features": [
                    {"name": "Elf Weapon Training", "description": "Proficiency with longswords and shortswords."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["ability_bonuses"] == [{"ability": "INT", "bonus": 1}]

        fetched = await client.get("/races/subraces/features", params={"race_id": race.id, "subrace_id": body["id"]})
        assert fetched.status_code == 200
        assert [item["name"] for item in fetched.json()] == ["Elf Weapon Training"]

    async def test_create_subrace_for_missing_race_returns_404(self, client, gm_token):
        response = await client.post(
            "/races/subraces",
            params={"race_id": 9999},
            json={"name": "High Elf"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_create_duplicate_subrace_name_returns_400(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        await create_subrace(race_id=race.id, name="High Elf")

        response = await client.post(
            "/races/subraces",
            params={"race_id": race.id},
            json={"name": "High Elf"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_list_subraces_for_race(self, client, create_race, create_subrace):
        elf = await create_race(name="Elf")
        dwarf = await create_race(name="Dwarf")
        await create_subrace(race_id=elf.id, name="High Elf")
        await create_subrace(race_id=elf.id, name="Drow")
        await create_subrace(race_id=dwarf.id, name="Hill Dwarf")

        response = await client.get("/races/subraces", params={"race_id": elf.id})

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Drow", "High Elf"]

    async def test_list_subraces_for_missing_race_returns_404(self, client):
        assert (await client.get("/races/subraces", params={"race_id": 9999})).status_code == 404

    async def test_get_subrace_scoped_to_race(self, client, create_race, create_subrace):
        elf = await create_race(name="Elf")
        dwarf = await create_race(name="Dwarf")
        subrace = await create_subrace(race_id=elf.id, name="High Elf")

        assert (await client.get(f"/races/subraces/{subrace.id}", params={"race_id": elf.id})).status_code == 200
        assert (await client.get(f"/races/subraces/{subrace.id}", params={"race_id": dwarf.id})).status_code == 404

    async def test_gm_can_update_subrace(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.patch(
            "/races/subraces",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"name": "Sun Elf", "description": "Reclusive scholars."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Sun Elf"
        assert response.json()["description"] == "Reclusive scholars."

    async def test_player_cannot_update_subrace(self, client, player_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.patch(
            "/races/subraces",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_cannot_delete_subrace(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="Doomed")

        response = await client.delete(
            "/races/subraces",
            params={"race_id": race.id, "subrace_id": subrace.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 403
        assert (await client.get(f"/races/subraces/{subrace.id}", params={"race_id": race.id})).status_code == 200

    async def test_founder_can_delete_subrace(self, client, founder_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="Doomed")

        response = await client.delete(
            "/races/subraces",
            params={"race_id": race.id, "subrace_id": subrace.id},
            headers={"Authorization": f"Bearer {founder_token}"},
        )

        assert response.status_code == 204
        assert (await client.get(f"/races/subraces/{subrace.id}", params={"race_id": race.id})).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceAbilityBonuses:
    async def test_gm_can_replace_ability_bonuses(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.put(
            "/races/subraces/ability-bonuses",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"ability_bonuses": [{"ability": "INT", "bonus": 1}, {"ability": "DEX", "bonus": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [(item["ability"], item["bonus"]) for item in response.json()["ability_bonuses"]] == [
            ("INT", 1),
            ("DEX", 1),
        ]

    async def test_ability_bonuses_full_replace(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        await client.put(
            "/races/subraces/ability-bonuses",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"ability_bonuses": [{"ability": "INT", "bonus": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.put(
            "/races/subraces/ability-bonuses",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"ability_bonuses": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["ability_bonuses"] == []

    async def test_duplicate_ability_bonus_returns_422(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.put(
            "/races/subraces/ability-bonuses",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"ability_bonuses": [{"ability": "INT", "bonus": 1}, {"ability": "INT", "bonus": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_player_cannot_set_ability_bonuses(self, client, player_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.put(
            "/races/subraces/ability-bonuses",
            params={"race_id": race.id, "subrace_id": subrace.id},
            json={"ability_bonuses": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_set_ability_bonuses_scoped_to_race(self, client, gm_token, create_race, create_subrace):
        elf = await create_race(name="Elf")
        dwarf = await create_race(name="Dwarf")
        subrace = await create_subrace(race_id=elf.id, name="High Elf")

        response = await client.put(
            "/races/subraces/ability-bonuses",
            params={"race_id": dwarf.id, "subrace_id": subrace.id},
            json={"ability_bonuses": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceFeatures:
    async def test_player_cannot_add_subrace_feature(self, client, player_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.post(
            "/features",
            json={"name": "Elf Weapon Training", "source_type": "SUBRACE", "subrace_id": subrace.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_add_update_and_remove_subrace_features(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        added = await client.post(
            "/features",
            json={
                "name": "Elf Weapon Training",
                "description": "Proficiency with longswords.",
                "source_type": "SUBRACE",
                "subrace_id": subrace.id,
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature = added.json()
        assert feature["name"] == "Elf Weapon Training"
        assert feature["level"] is None

        updated = await client.patch(
            f"/features/{feature['id']}",
            json={"description": "Proficiency with longswords and shortswords."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Proficiency with longswords and shortswords."

        removed = await client.delete(
            f"/features/{feature['id']}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        assert (
            await client.get("/races/subraces/features", params={"race_id": race.id, "subrace_id": subrace.id})
        ).json() == []

    async def test_gm_can_add_subrace_feature_with_level(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.post(
            "/features",
            json={"name": "Elf Weapon Training", "source_type": "SUBRACE", "subrace_id": subrace.id, "level": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["level"] == 3

    async def test_subrace_features_scoped_to_race(self, client, gm_token, create_race, create_subrace):
        elf = await create_race(name="Elf")
        dwarf = await create_race(name="Dwarf")
        subrace = await create_subrace(race_id=elf.id, name="High Elf")

        response = await client.get("/races/subraces/features", params={"race_id": dwarf.id, "subrace_id": subrace.id})

        assert response.status_code == 404
