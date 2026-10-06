"""Negative and boundary tests for the character attack endpoints."""

import pytest

from app.features.characters.attacks.service import MAX_ATTACKS_PER_CHARACTER
from app.models import Attack

ATTACK_PAYLOAD = {
    "name": "Longsword",
    "attack_type": "MELEE_ATTACK",
    "ability": "STR",
    "damage_dice_count": 1,
    "damage_dice_type": "D8",
    "damage_type": "SLASHING",
}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def make_attack(client, token, character_id, **overrides):
    return await client.post(
        f"/characters/{character_id}/attacks", json={**ATTACK_PAYLOAD, **overrides}, headers=auth(token)
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterAttacksHardening:
    async def test_another_characters_attack_id_is_not_reachable_through_my_character(
        self, client, player, player_token, gm_token, create_user, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        other = await create_user()
        mine = await create_character(owner_id=player.id, class_id=fighter.id)
        theirs = await create_character(owner_id=other.id, class_id=fighter.id)
        mine_id, theirs_id = mine.id, theirs.id
        foreign_attack_id = (await make_attack(client, gm_token, theirs_id)).json()["id"]

        patch = await client.patch(
            f"/characters/{mine_id}/attacks/{foreign_attack_id}", json={"name": "Stolen"}, headers=auth(player_token)
        )
        delete = await client.delete(f"/characters/{mine_id}/attacks/{foreign_attack_id}", headers=auth(player_token))

        assert patch.status_code == 404
        assert delete.status_code == 404
        listing = await client.get(f"/characters/{theirs_id}/attacks", headers=auth(gm_token))
        assert [a["name"] for a in listing.json()] == ["Longsword"]

    async def test_unknown_enum_values_are_a_422(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        for overrides in (
            {"attack_type": "NOPE"},
            {"ability": "LUCK"},
            {"damage_type": "SPICY"},
            {"damage_dice_type": "D7"},
        ):
            response = await make_attack(client, player_token, character.id, **overrides)
            assert response.status_code == 422, overrides

    async def test_out_of_bounds_values_are_a_422(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        for overrides in (
            {"name": ""},
            {"name": "x" * 201},
            {"range": "x" * 51},
            {"damage_dice_count": -1},
            {"damage_dice_count": 2_000_000_000},
            {"bonus_attack": 10_000},
        ):
            response = await make_attack(client, player_token, character.id, **overrides)
            assert response.status_code == 422, overrides

    async def test_patch_with_null_for_a_required_field_is_a_422(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        attack_id = (await make_attack(client, player_token, character.id)).json()["id"]

        for field in ("name", "attack_type", "ability", "range", "notes", "bonus_attack"):
            response = await client.patch(
                f"/characters/{character.id}/attacks/{attack_id}", json={field: None}, headers=auth(player_token)
            )
            assert response.status_code == 422, field

    async def test_patch_can_clear_the_optional_damage_fields(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        attack_id = (await make_attack(client, player_token, character.id)).json()["id"]

        response = await client.patch(
            f"/characters/{character.id}/attacks/{attack_id}",
            json={"damage_dice_count": None, "damage_dice_type": None, "damage_type": None},
            headers=auth(player_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["damage_dice_count"], body["damage_dice_type"], body["damage_type"]) == (None, None, None)

    async def test_attack_count_is_capped_per_character(
        self, client, db_session, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        db_session.add_all(
            Attack(character_id=character.id, name=f"A{i}", attack_type="MELEE_ATTACK", ability="STR")
            for i in range(MAX_ATTACKS_PER_CHARACTER)
        )
        await db_session.commit()

        response = await make_attack(client, player_token, character.id)

        assert response.status_code == 400

    async def test_gm_can_manage_any_characters_attacks(self, client, gm_token, player, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        assert (await make_attack(client, gm_token, character.id)).status_code == 201

    async def test_unknown_character_is_404(self, client, player_token):
        assert (await make_attack(client, player_token, 999999)).status_code == 404
