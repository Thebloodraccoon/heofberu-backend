"""
Integration tests for combat stats: derived hit dice/speed, the editable armor_class column and the computed
``GET /characters/{id}/combat-stats``.
"""

import pytest

from tests.helpers import set_effects


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def give_item(client, gm_token, character_id, item_id):
    """Add a stack via the GM panel (it arrives unequipped); returns the stack id."""

    response = await client.post(
        f"/characters/{character_id}/gm-panel/items", json={"item_id": item_id}, headers=auth(gm_token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def equip(client, token, character_id, stack_id, on=True):
    response = await client.patch(
        f"/characters/{character_id}/items/{stack_id}", json={"is_equipped": on}, headers=auth(token)
    )
    assert response.status_code == 200, response.text


async def combat_stats(client, token, character_id):
    response = await client.get(f"/characters/{character_id}/combat-stats", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def add_item_effects(client, gm_token, item_id, static_groups):
    response = await client.post(
        f"/items/{item_id}/effects", json={"static_groups": static_groups}, headers=auth(gm_token)
    )
    assert response.status_code == 200, response.text


async def grant_with_effects(client, gm_token, character_id, feature_id, static_groups):
    """Give the feature fixed effects, then grant it through the GM panel."""

    effects = await set_effects(client, gm_token, feature_id, {"static_groups": static_groups})
    assert effects.status_code == 200, effects.text
    grant = await client.post(
        f"/characters/{character_id}/gm-panel/features", json={"feature_id": feature_id}, headers=auth(gm_token)
    )
    assert grant.status_code == 201, grant.text


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

    async def _create_armor(self, client, gm_token, name, base, category, max_dex_bonus=None):
        response = await client.post(
            "/items/armor",
            json={
                "name": name,
                "armor": {
                    "armor_category": category,
                    "armor_class_base": base,
                    "armor_class_max_dex_bonus": max_dex_bonus,
                },
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
        armor_id = await self._create_armor(client, gm_token, "Scale Mail", base=14, category="MEDIUM", max_dex_bonus=2)

        add_response = await client.post(
            f"/characters/{character['id']}/gm-panel/items",
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


@pytest.mark.integration
@pytest.mark.asyncio
class TestCombatStats:
    async def test_stranger_gets_403_and_unknown_character_404(
        self, client, player, player_token, create_user, login_as, create_class, create_api_character
    ):
        character, _ = await create_api_character(class_id=(await create_class(name="Fighter")).id, owner=player)
        stranger_token = await login_as(await create_user())

        stranger = await client.get(f"/characters/{character['id']}/combat-stats", headers=auth(stranger_token))
        unknown = await client.get("/characters/999999/combat-stats", headers=auth(player_token))

        assert (stranger.status_code, unknown.status_code) == (403, 404)

    async def test_equipped_armor_and_shield_make_the_computed_ac(
        self, client, gm_token, player, create_class, create_item, create_api_character
    ):
        character, token = await create_api_character(
            class_id=(await create_class(name="Fighter")).id, owner=player, dexterity=14
        )
        scale = await create_item(name="Scale Mail", kind="ARMOR", armor_category="MEDIUM", armor_class_base=14)
        shield = await create_item(name="Shield", kind="ARMOR", armor_category="SHIELD", armor_class_base=2)
        stacks = [await give_item(client, gm_token, character["id"], item.id) for item in (scale, shield)]

        unarmored = await combat_stats(client, token, character["id"])
        for stack_id in stacks:
            await equip(client, token, character["id"], stack_id)
        armored = await combat_stats(client, token, character["id"])

        assert unarmored["armor_class"]["computed"] == 12
        assert armored["armor_class"]["computed"] == 14 + 2 + 2
        assert [line["source"] for line in armored["armor_class"]["breakdown"]] == ["armor", "ability", "shield"]
        assert armored["armor_class"]["manual"] == 10

    async def test_grant_speed_and_ac_effects_are_applied(
        self, client, gm_token, player, create_class, create_feature, create_api_character
    ):
        character, token = await create_api_character(
            class_id=(await create_class(name="Monk")).id, owner=player, dexterity=14
        )
        feature = await create_feature(name="Swift Guard", source_type="CLASS", level=None)
        await grant_with_effects(
            client,
            gm_token,
            character["id"],
            feature.id,
            [
                {"effect_type": "speed", "items": [{"value": 10}]},
                {"effect_type": "armor_class", "items": [{"value": 1}]},
            ],
        )

        stats = await combat_stats(client, token, character["id"])

        assert stats["armor_class"]["computed"] == 10 + 2 + 1
        assert stats["speed"]["computed"]["walk"] == 30 + 10
        assert ("bonus", "Swift Guard") in {(line["source"], line["label"]) for line in stats["speed"]["breakdown"]}

    async def test_item_effects_apply_only_while_equipped(
        self, client, gm_token, player, create_class, create_item, create_api_character
    ):
        character, token = await create_api_character(class_id=(await create_class(name="Fighter")).id, owner=player)
        boots = await create_item(name="Boots of Striding", kind="GEAR")
        await add_item_effects(client, gm_token, boots.id, [{"effect_type": "speed", "items": [{"value": 5}]}])
        stack_id = await give_item(client, gm_token, character["id"], boots.id)

        carried = await combat_stats(client, token, character["id"])
        await equip(client, token, character["id"], stack_id)
        worn = await combat_stats(client, token, character["id"])

        assert (carried["speed"]["computed"]["walk"], worn["speed"]["computed"]["walk"]) == (30, 35)

    async def test_item_needing_attunement_applies_only_once_attuned(
        self, client, gm_token, player, create_class, create_item, create_api_character
    ):
        character, token = await create_api_character(class_id=(await create_class(name="Fighter")).id, owner=player)
        cloak = await create_item(name="Cloak of Protection", kind="GEAR", requires_attunement=True)
        await add_item_effects(client, gm_token, cloak.id, [{"effect_type": "armor_class", "items": [{"value": 1}]}])
        stack_id = await give_item(client, gm_token, character["id"], cloak.id)
        await equip(client, token, character["id"], stack_id)

        unattuned = await combat_stats(client, token, character["id"])
        attune = await client.patch(
            f"/characters/{character['id']}/gm-panel/items",
            params={"item_id": stack_id},
            json={"is_attuned": True},
            headers=auth(gm_token),
        )
        assert attune.status_code == 200, attune.text
        attuned = await combat_stats(client, token, character["id"])

        assert (unattuned["armor_class"]["computed"], attuned["armor_class"]["computed"]) == (10, 11)

    async def test_without_a_race_walking_starts_at_the_default(
        self, client, player, create_class, create_api_character
    ):
        character, token = await create_api_character(class_id=(await create_class(name="Fighter")).id, owner=player)

        stats = await combat_stats(client, token, character["id"])

        assert stats["speed"]["computed"]["walk"] == 30
        assert stats["speed"]["breakdown"][0] == {
            "source": "base",
            "label": "Базовая скорость",
            "value": 30,
            "speed_type": "WALK",
            "reason": None,
            "reason_code": None,
        }

    async def test_inactive_lines_carry_a_reason_code(
        self, client, gm_token, player, create_class, create_feature, create_api_character
    ):
        character, token = await create_api_character(class_id=(await create_class(name="Fighter")).id, owner=player)
        feature = await create_feature(name="Armored Grace", source_type="CLASS", level=None)
        await grant_with_effects(
            client,
            gm_token,
            character["id"],
            feature.id,
            [{"effect_type": "armor_class", "items": [{"value": 1, "condition": "WEARING_ARMOR"}]}],
        )

        stats = await combat_stats(client, token, character["id"])

        assert [(line["label"], line["reason_code"]) for line in stats["armor_class"]["inactive"]] == [
            ("Armored Grace", "condition_unmet")
        ]
