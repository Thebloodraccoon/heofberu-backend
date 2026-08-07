"""Integration tests for derived combat stats: hit dice, speed, armor class."""

import pytest


@pytest.mark.integration
class TestDerivedHitDice:
    def test_hit_dice_comes_from_class(self, client, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter", hit_dice="D10")

        character, _ = create_api_character(class_id=character_class.id, owner=player)

        assert character["hit_dice"] == "D10"

    def test_hit_dice_updates_on_class_change(self, client, player, player_token, create_class, create_api_character):
        fighter = create_class(name="Fighter", hit_dice="D10")
        wizard = create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        character, token = create_api_character(class_id=fighter.id, owner=player)
        assert character["hit_dice"] == "D10"

        response = client.patch(
            f"/characters/{character['id']}/progression/class",
            json={"class_id": wizard.id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["hit_dice"] == "D6"


@pytest.mark.integration
class TestDerivedSpeed:
    def test_speed_comes_from_race(self, client, player, player_token, create_class, create_race, create_api_character):
        character_class = create_class(name="Fighter")
        race = create_race(name="Dwarf", speed=25)

        character, _ = create_api_character(class_id=character_class.id, owner=player, race_id=race.id)

        assert character["speed"] == 25

    def test_speed_defaults_to_thirty_without_race(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter")

        character, _ = create_api_character(class_id=character_class.id, owner=player)

        assert character["speed"] == 30

    def test_speed_updates_on_race_change(
        self, client, player, player_token, create_class, create_race, create_api_character
    ):
        character_class = create_class(name="Fighter")
        race = create_race(name="Dwarf", speed=25)
        character, token = create_api_character(class_id=character_class.id, owner=player)
        assert character["speed"] == 30

        response = client.patch(
            f"/characters/{character['id']}/progression/race",
            json={"race_id": race.id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["speed"] == 25


@pytest.mark.integration
class TestDerivedArmorClass:
    def _create_armor(self, client, gm_token, name, base, dex_bonus, max_dex_bonus=None):
        response = client.post(
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

    def _equip(self, client, token, character_id, item_id, is_equipped):
        response = client.post(
            f"/characters/{character_id}/items/",
            json={"item_id": item_id, "is_equipped": is_equipped},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_unarmored_ac_is_ten_plus_dex_modifier(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter")

        character, _ = create_api_character(class_id=character_class.id, owner=player, dexterity=14)

        assert character["armor_class"] == 12

    def test_equipped_armor_uses_base_plus_dex(
        self, client, gm_token, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter")
        character, token = create_api_character(class_id=character_class.id, owner=player, dexterity=14)
        armor_id = self._create_armor(client, gm_token, "Leather", base=11, dex_bonus=True)
        self._equip(client, token, character["id"], armor_id, is_equipped=True)

        response = client.get(f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["armor_class"] == 13

    def test_armor_dex_bonus_is_capped(
        self, client, gm_token, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter")
        character, token = create_api_character(class_id=character_class.id, owner=player, dexterity=18)
        armor_id = self._create_armor(client, gm_token, "Scale Mail", base=14, dex_bonus=True, max_dex_bonus=2)
        self._equip(client, token, character["id"], armor_id, is_equipped=True)

        response = client.get(f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["armor_class"] == 16

    def test_heavy_armor_ignores_dex(self, client, gm_token, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter")
        character, token = create_api_character(class_id=character_class.id, owner=player, dexterity=18)
        armor_id = self._create_armor(client, gm_token, "Plate", base=18, dex_bonus=False)
        self._equip(client, token, character["id"], armor_id, is_equipped=True)

        response = client.get(f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["armor_class"] == 18

    def test_unequipping_armor_restores_unarmored_ac(
        self, client, gm_token, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter")
        character, token = create_api_character(class_id=character_class.id, owner=player, dexterity=14)
        armor_id = self._create_armor(client, gm_token, "Leather", base=11, dex_bonus=True)
        stack = self._equip(client, token, character["id"], armor_id, is_equipped=True)

        unequip_response = client.patch(
            f"/characters/{character['id']}/items/{stack['id']}",
            json={"is_equipped": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert unequip_response.status_code == 200

        response = client.get(f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["armor_class"] == 12

    def test_derived_stats_reflected_in_listing(
        self, client, player, player_token, create_class, create_race, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        race = create_race(name="Elf")
        character, token = create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, dexterity=14
        )

        response = client.get("/characters/", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        row = next(item for item in response.json()["items"] if item["id"] == character["id"])
        assert row["hit_dice"] == "D10"
        assert row["speed"] == 30
        assert row["armor_class"] == 12
