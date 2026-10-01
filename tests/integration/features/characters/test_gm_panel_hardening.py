"""
GM-panel behaviour pinned after the audit fixes: re-granting a proficiency after a GM veto, GM-owned
expertise, input bounds, atomic ASI/max-level writes and reference-existence checks (404 instead of FK 400).
"""

import pytest
from sqlalchemy import delete, func, select

from app.models import CharacterMaxLevel
from app.models.character.character_asi_choice_model import CharacterASIChoice

PROFICIENCIES = "/characters/{character_id}/gm-panel/proficiencies"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def put_effects_and_grant(client, gm_token, character_id, feature_id, effects) -> int:
    """Set a feature's effects and grant it to the character; returns the grant id."""

    fx_resp = await client.put(f"/features/{feature_id}/effects", json=effects, headers=auth(gm_token))
    assert fx_resp.status_code == 200, fx_resp.text

    grant_resp = await client.post(
        f"/characters/{character_id}/gm-panel/features", json={"feature_id": feature_id}, headers=auth(gm_token)
    )
    assert grant_resp.status_code == 201, grant_resp.text
    return grant_resp.json()["id"]


async def read_skills(client, token, character_id) -> dict[int, dict]:
    response = await client.get(f"/characters/{character_id}/proficiencies", headers=auth(token))
    assert response.status_code == 200, response.text
    return {skill["skill_id"]: skill for skill in response.json()["skills"]}


@pytest.mark.integration
@pytest.mark.asyncio
class TestRegrantAfterGmVeto:
    async def test_regranting_a_feature_skill_after_revoke_succeeds_and_restores_the_feature_source(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Sneaky", source_type="CLASS", level=None)
        await put_effects_and_grant(
            client, gm_token, character.id, feature.id, {"skill_effects": [{"skill_id": skill.id}]}
        )
        url = PROFICIENCIES.format(character_id=character.id) + "/skills"

        revoke = await client.delete(url, params={"skill_id": skill.id}, headers=auth(gm_token))
        assert revoke.status_code == 204, revoke.text
        assert skill.id not in await read_skills(client, gm_token, character.id)

        regrant = await client.post(url, json={"skill_id": skill.id}, headers=auth(gm_token))

        assert regrant.status_code == 201, regrant.text
        assert regrant.json() == {"skill_id": skill.id, "is_expertise": False}
        skills = await read_skills(client, gm_token, character.id)
        assert [source["source_type"] for source in skills[skill.id]["sources"]] == ["FEATURE"]

    async def test_regranting_after_the_vetoed_source_is_gone_grants_the_skill_to_the_gm_layer(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Sneaky", source_type="CLASS", level=None)
        grant_id = await put_effects_and_grant(
            client, gm_token, character.id, feature.id, {"skill_effects": [{"skill_id": skill.id}]}
        )
        url = PROFICIENCIES.format(character_id=character.id) + "/skills"
        await client.delete(url, params={"skill_id": skill.id}, headers=auth(gm_token))
        removal = await client.delete(
            f"/characters/{character.id}/gm-panel/features", params={"feature_id": grant_id}, headers=auth(gm_token)
        )
        assert removal.status_code == 204, removal.text

        regrant = await client.post(url, json={"skill_id": skill.id}, headers=auth(gm_token))

        assert regrant.status_code == 201, regrant.text
        skills = await read_skills(client, gm_token, character.id)
        assert [source["source_type"] for source in skills[skill.id]["sources"]] == ["GM"]

    async def test_removing_a_gm_grant_that_a_feature_also_gives_keeps_it_revoked(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Sneaky", source_type="CLASS", level=None)
        url = PROFICIENCIES.format(character_id=character.id) + "/skills"
        add = await client.post(url, json={"skill_id": skill.id}, headers=auth(gm_token))
        assert add.status_code == 201, add.text
        await put_effects_and_grant(
            client, gm_token, character.id, feature.id, {"skill_effects": [{"skill_id": skill.id}]}
        )

        removal = await client.delete(url, params={"skill_id": skill.id}, headers=auth(gm_token))

        assert removal.status_code == 204, removal.text
        assert skill.id not in await read_skills(client, gm_token, character.id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmOwnsExpertise:
    async def test_gm_can_clear_expertise_a_feature_grants(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Master Sneak", source_type="CLASS", level=None)
        await put_effects_and_grant(
            client,
            gm_token,
            character.id,
            feature.id,
            {"skill_effects": [{"skill_id": skill.id, "grants_expertise": True}]},
        )
        assert (await read_skills(client, gm_token, character.id))[skill.id]["is_expertise"] is True
        url = PROFICIENCIES.format(character_id=character.id) + "/skills/expertise"

        cleared = await client.patch(
            url, params={"skill_id": skill.id}, json={"is_expertise": False}, headers=auth(gm_token)
        )

        assert cleared.status_code == 200, cleared.text
        assert cleared.json() == {"skill_id": skill.id, "is_expertise": False}
        assert (await read_skills(client, gm_token, character.id))[skill.id]["is_expertise"] is False

        restored = await client.patch(
            url, params={"skill_id": skill.id}, json={"is_expertise": True}, headers=auth(gm_token)
        )
        assert restored.json()["is_expertise"] is True

    async def test_gm_added_skill_does_not_pin_expertise_to_false(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        """A plain GM grant makes no expertise decision, so a feature granted later can still give expertise."""

        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Master Sneak", source_type="CLASS", level=None)
        url = PROFICIENCIES.format(character_id=character.id) + "/skills"
        assert (await client.post(url, json={"skill_id": skill.id}, headers=auth(gm_token))).status_code == 201

        await put_effects_and_grant(
            client,
            gm_token,
            character.id,
            feature.id,
            {"skill_effects": [{"skill_id": skill.id, "grants_expertise": True}]},
        )

        assert (await read_skills(client, gm_token, character.id))[skill.id]["is_expertise"] is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestProficiencyReferenceChecks:
    async def test_unknown_skill_is_404(self, client, gm, gm_token, create_class, create_character):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)

        response = await client.post(
            PROFICIENCIES.format(character_id=character.id) + "/skills",
            json={"skill_id": 999_999},
            headers=auth(gm_token),
        )

        assert response.status_code == 404

    async def test_unknown_weapon_item_is_404(self, client, gm, gm_token, create_class, create_character):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)

        response = await client.post(
            PROFICIENCIES.format(character_id=character.id) + "/weapons",
            json={"item_id": 999_999},
            headers=auth(gm_token),
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("body", [{"skill_id": 0}, {"skill_id": -3}])
    async def test_non_positive_skill_id_is_422(self, client, gm, gm_token, create_class, create_character, body):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)

        response = await client.post(
            PROFICIENCIES.format(character_id=character.id) + "/skills", json=body, headers=auth(gm_token)
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("body", [{}, {"weapon_category": "MARTIAL", "item_id": 1}])
    async def test_weapon_needs_exactly_one_target(self, client, gm, gm_token, create_class, create_character, body):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)

        response = await client.post(
            PROFICIENCIES.format(character_id=character.id) + "/weapons", json=body, headers=auth(gm_token)
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestInputBounds:
    @pytest.mark.parametrize(
        "increases",
        [
            [],
            [{"ability": "STR", "amount": 0}],
            [{"ability": "STR", "amount": 31}],
            [{"ability": "STR", "amount": -31}],
            [{"ability": "STR", "amount": 2_147_483_647}],
        ],
    )
    async def test_asi_adjustment_bounds_are_422(self, client, gm, gm_token, create_class, create_character, increases):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/asi", json={"increases": increases}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("max_hp", [-1, 10_001, 2_147_483_648])
    async def test_max_hp_bounds_are_422(self, client, gm, gm_token, create_class, create_character, max_hp):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/max-hp", json={"max_hp": max_hp}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_zero_max_hp_is_still_allowed(self, client, gm, gm_token, create_class, create_character):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/max-hp", json={"max_hp": 0}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 0

    @pytest.mark.parametrize("quantity", [0, -1, 1_000_001])
    async def test_item_add_quantity_bounds_are_422(
        self, client, gm, gm_token, create_class, create_character, create_item, quantity
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)
        item = await create_item(name="Rope")

        response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": quantity},
            headers=auth(gm_token),
        )

        assert response.status_code == 422

    async def test_merging_into_a_full_stack_is_rejected(
        self, client, gm, gm_token, create_class, create_character, create_item
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)
        item = await create_item(name="Arrow")
        url = f"/characters/{character.id}/gm-panel/items"
        full = await client.post(url, json={"item_id": item.id, "quantity": 1_000_000}, headers=auth(gm_token))
        assert full.status_code == 201, full.text

        response = await client.post(url, json={"item_id": item.id, "quantity": 1}, headers=auth(gm_token))

        assert response.status_code == 400

    @pytest.mark.parametrize("spell_id", [0, -1])
    async def test_non_positive_spell_ids_are_422(self, client, gm, gm_token, create_class, create_character, spell_id):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Wizard")).id)

        known = await client.post(
            f"/characters/{character.id}/spells", json={"spell_id": spell_id}, headers=auth(gm_token)
        )
        granted = await client.post(
            f"/characters/{character.id}/gm-panel/spells", json={"spell_id": spell_id}, headers=auth(gm_token)
        )

        assert known.status_code == 422
        assert granted.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestAsiAtomicity:
    async def test_rejected_over_cap_adjustment_leaves_no_row_and_no_stale_totals(
        self, client, gm, gm_token, db_session, create_class, create_character
    ):
        character = await create_character(
            owner_id=gm.id, class_id=(await create_class(name="Fighter")).id, strength=29
        )
        character_id = character.id

        rejected = await client.post(
            f"/characters/{character_id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 2}]},
            headers=auth(gm_token),
        )

        assert rejected.status_code == 400
        listed = await client.get(f"/characters/{character_id}/gm-panel/asi", headers=auth(gm_token))
        assert listed.json() == []
        rows = await db_session.scalar(
            select(func.count()).select_from(CharacterASIChoice).where(CharacterASIChoice.character_id == character_id)
        )
        assert rows == 0
        stats = (await client.get(f"/characters/{character_id}/stats", headers=auth(gm_token))).json()
        assert stats["strength"]["total"] == 29

    async def test_adjustments_list_in_creation_order_and_exclude_level_tied_choices(
        self, client, gm, gm_token, create_class, create_character
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)
        url = f"/characters/{character.id}/gm-panel/asi"

        first = await client.post(url, json={"increases": [{"ability": "STR", "amount": 1}]}, headers=auth(gm_token))
        second = await client.post(url, json={"increases": [{"ability": "DEX", "amount": 1}]}, headers=auth(gm_token))

        listed = await client.get(url, headers=auth(gm_token))

        assert [row["id"] for row in listed.json()] == [first.json()["id"], second.json()["id"]]

    async def test_totals_are_fresh_right_after_the_write_and_after_removal(
        self, client, gm, gm_token, create_class, create_character
    ):
        character = await create_character(
            owner_id=gm.id, class_id=(await create_class(name="Fighter")).id, strength=10
        )
        base = f"/characters/{character.id}"

        added = await client.post(
            f"{base}/gm-panel/asi", json={"increases": [{"ability": "STR", "amount": 4}]}, headers=auth(gm_token)
        )
        assert (await client.get(f"{base}/stats", headers=auth(gm_token))).json()["strength"]["total"] == 14

        removed = await client.delete(
            f"{base}/gm-panel/asi", params={"adjustment_id": added.json()["id"]}, headers=auth(gm_token)
        )
        assert removed.status_code == 204
        assert (await client.get(f"{base}/stats", headers=auth(gm_token))).json()["strength"]["total"] == 10


@pytest.mark.integration
@pytest.mark.asyncio
class TestMaxLevelAtomicity:
    @staticmethod
    async def _without_cap_row(db_session, character_id):
        """Drop the cap row the fixture seeded: legacy characters may have none (cap = current level)."""

        await db_session.execute(delete(CharacterMaxLevel).where(CharacterMaxLevel.character_id == character_id))
        await db_session.commit()

    async def test_rejected_raise_seeds_no_row(self, client, gm, gm_token, db_session, create_class, create_character):
        """A character without a cap row keeps none when the GM's value is rejected."""

        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id, level=3)
        character_id = character.id
        await self._without_cap_row(db_session, character_id)

        rejected = await client.patch(
            f"/characters/{character_id}/gm-panel/max-level", json={"max_level": 3}, headers=auth(gm_token)
        )

        assert rejected.status_code == 400
        rows = await db_session.scalar(
            select(func.count()).select_from(CharacterMaxLevel).where(CharacterMaxLevel.character_id == character_id)
        )
        assert rows == 0

    async def test_first_raise_seeds_the_row_at_the_new_value(
        self, client, gm, gm_token, db_session, create_class, create_character
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id, level=3)
        character_id = character.id
        await self._without_cap_row(db_session, character_id)

        raised = await client.patch(
            f"/characters/{character_id}/gm-panel/max-level", json={"max_level": 6}, headers=auth(gm_token)
        )

        assert raised.status_code == 200
        assert raised.json() == {"character_id": character_id, "current_level": 3, "max_level": 6}
        stored = await db_session.scalar(
            select(CharacterMaxLevel.max_level).where(CharacterMaxLevel.character_id == character_id)
        )
        assert stored == 6

    async def test_stranger_cannot_read_max_level(self, client, gm, player_token, create_class, create_character):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)

        response = await client.get(f"/characters/{character.id}/gm-panel/max-level", headers=auth(player_token))

        assert response.status_code in (403, 404)
