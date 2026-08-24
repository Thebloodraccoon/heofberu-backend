"""Integration tests for combat stats: derived hit dice/speed and the editable armor_class column."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestDerivedHitDice:
    async def test_hit_dice_comes_from_class(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter", hit_dice="D10")

        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        assert character["hit_dice"] == "D10"


@pytest.mark.integration
@pytest.mark.asyncio
class TestDerivedSpeed:
    async def test_speed_comes_from_race(
        self, client, player, player_token, create_class, create_race, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        race = await create_race(name="Dwarf", speed=25)

        character, _ = await create_api_character(class_id=character_class.id, owner=player, race_id=race.id)

        assert character["speed"] == 25

    async def test_speed_defaults_to_thirty_without_race(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")

        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        assert character["speed"] == 30


@pytest.mark.integration
@pytest.mark.asyncio
class TestEditableArmorClass:
    """
    Armor class is a plain editable column: there is NO dynamic armor
    calculation anymore — equipping an ARMOR item does not touch it, and
    players/GMs set it directly on create or via PATCH.
    """

    async def _create_armor(self, client, gm_token, name, base, dex_bonus, max_dex_bonus=None):
        response = await client.post(
            "/items",
            json={
                "name": name,
                "item_type": "ARMOR",
                "armor_class_base": base,
                "armor_class_dex_bonus": dex_bonus,
                "armor_class_max_dex_bonus": max_dex_bonus,
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def test_armor_class_defaults_to_ten(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter")

        character, _ = await create_api_character(class_id=character_class.id, owner=player, dexterity=14)

        assert character["armor_class"] == 10

    async def test_armor_class_set_at_creation(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter")

        character, _ = await create_api_character(class_id=character_class.id, owner=player, armor_class=16)

        assert character["armor_class"] == 16

    async def test_armor_class_is_patchable(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}",
            json={"armor_class": 18, "shield": 2},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["armor_class"] == 18
        assert response.json()["shield"] == 2

    async def test_equipped_armor_does_not_change_ac(
        self, client, gm_token, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=character_class.id, owner=player, armor_class=12)
        armor_id = await self._create_armor(client, gm_token, "Scale Mail", base=14, dex_bonus=True, max_dex_bonus=2)

        add_response = await client.post(
            "/characters/gm-panel/items",
            params={"character_id": character["id"]},
            json={"item_id": armor_id, "is_equipped": True},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201, add_response.text

        response = await client.get(f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["armor_class"] == 12

    async def test_derived_stats_reflected_in_listing(
        self, client, player, player_token, create_class, create_race, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        race = await create_race(name="Elf")
        character, token = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, dexterity=14
        )

        response = await client.get("/characters", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        row = next(item for item in response.json()["items"] if item["id"] == character["id"])
        assert row["hit_dice"] == "D10"
        assert row["speed"] == 30
        assert row["armor_class"] == 10
