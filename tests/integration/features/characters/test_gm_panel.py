"""Tests for the GM panel: max HP writes, stats overview, free-form ASI adjustments, skill expertise."""

import pytest

from app.models.character_association_models import CharacterSkillProficiency


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelMaxHp:
    async def test_set_max_hp_clamps_current_hp(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, max_hp=20, current_hp=20)

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/max-hp",
            json={"max_hp": 12},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["max_hp"] == 12
        assert response.json()["current_hp"] == 12

    async def test_set_higher_max_hp_keeps_current(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, max_hp=10, current_hp=7)

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/max-hp",
            json={"max_hp": 18},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["max_hp"] == 18
        assert response.json()["current_hp"] == 7

    async def test_player_denied_max_hp_write(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/max-hp",
            json={"max_hp": 30},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelStats:
    async def test_stats_show_base_vs_total_without_bonuses(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=14, dexterity=10)

        response = await client.get(
            f"/characters/{character.id}/gm-panel/stats",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        stats = response.json()
        assert stats["strength"] == {"base": 14, "total": 14}
        assert stats["dexterity"] == {"base": 10, "total": 10}
        for ability in ("constitution", "intelligence", "wisdom", "charisma"):
            assert set(stats[ability]) == {"base", "total"}

    async def test_stats_reflect_asi_adjustment_freshly(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=14)

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201

        response = await client.get(
            f"/characters/{character.id}/gm-panel/stats",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        # Base stays at the originally entered value; the counted
        # adjustment lives in the ASI-choice log and lifts only the total.
        assert response.json()["strength"] == {"base": 14, "total": 16}


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelAsiAdjustments:
    async def test_add_and_list_adjustment(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={
                "increases": [
                    {"ability": "STR", "amount": 2},
                    {"ability": "DEX", "amount": -1},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201
        adjustment = add_response.json()
        assert {item["ability"]: item["amount"] for item in adjustment["increases"]} == {"STR": 2, "DEX": -1}

        list_response = await client.get(
            f"/characters/{character.id}/gm-panel/asi",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert list_response.status_code == 200
        assert [row["id"] for row in list_response.json()] == [adjustment["id"]]

    async def test_remove_adjustment_reverts_base_scores(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=13)

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 3}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        adjustment_id = add_response.json()["id"]

        remove_response = await client.delete(
            f"/characters/{character.id}/gm-panel/asi",
            params={"adjustment_id": adjustment_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_response.status_code == 204

        stats = (
            await client.get(
                f"/characters/{character.id}/gm-panel/stats",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        # Deleting the log row reverts the total; the base was never touched.
        assert stats["strength"] == {"base": 13, "total": 13}

        listed = await client.get(
            f"/characters/{character.id}/gm-panel/asi",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert listed.json() == []

    async def test_adjustment_above_thirty_returns_400(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=29)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400  # 31 > 30

    async def test_gm_can_raise_above_twenty_up_to_thirty(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=20)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201  # 22 > 20, but <= 30: the GM panel override applies

    async def test_duplicate_ability_in_increases_returns_422(
        self, client, gm, gm_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={
                "increases": [
                    {"ability": "STR", "amount": 1},
                    {"ability": "STR", "amount": 1},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_player_denied_asi_writes(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 5}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelSkillExpertise:
    async def test_gm_can_toggle_expertise_on_and_off(
        self, client, player, gm_token, db_session, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Rogue")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        db_session.add(CharacterSkillProficiency(character_id=character.id, skill_id=skill.id, is_expertise=False))
        await db_session.commit()

        on_response = await client.patch(
            f"/characters/{character.id}/gm-panel/skills",
            params={"skill_id": skill.id},
            json={"is_expertise": True},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert on_response.status_code == 200
        assert on_response.json() == {"skill_id": skill.id, "is_expertise": True}

        read_response = await client.get(
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        proficiencies = {item["skill_id"]: item for item in read_response.json()["skill_proficiencies"]}
        assert proficiencies[skill.id]["is_expertise"] is True

        off_response = await client.patch(
            f"/characters/{character.id}/gm-panel/skills",
            params={"skill_id": skill.id},
            json={"is_expertise": False},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert off_response.status_code == 200
        assert off_response.json()["is_expertise"] is False

    async def test_player_denied_expertise_write(
        self, client, player, player_token, db_session, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Rogue")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        db_session.add(CharacterSkillProficiency(character_id=character.id, skill_id=skill.id, is_expertise=False))
        await db_session.commit()

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/skills",
            params={"skill_id": skill.id},
            json={"is_expertise": True},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_expertise_without_proficiency_returns_404(
        self, client, player, gm_token, create_class, create_character, create_skill
    ):
        """Expertise requires an existing proficiency row — no row means a 404."""
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/skills",
            params={"skill_id": skill.id},
            json={"is_expertise": True},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
