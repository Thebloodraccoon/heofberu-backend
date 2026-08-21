"""Tests for character proficiency endpoints (skills and saving throws)."""

import pytest

from app.models.class_association_models import class_available_skills


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterSkillProficiencies:
    async def test_replace_skill_proficiencies(
        self, client, player, player_token, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        skill = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={"skill_proficiencies": [{"skill_id": skill.id, "is_expertise": True}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        proficiencies = response.json()["skill_proficiencies"]
        assert len(proficiencies) == 1
        assert proficiencies[0]["skill_id"] == skill.id
        assert proficiencies[0]["is_expertise"] is True

    async def test_clear_skill_proficiencies(
        self, client, player, player_token, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")

        await client.put(
            f"/characters/{character.id}/skills",
            json={"skill_proficiencies": [{"skill_id": skill.id, "is_expertise": False}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={"skill_proficiencies": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["skill_proficiencies"] == []

    async def test_invalid_skill_id_returns_400(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={"skill_proficiencies": [{"skill_id": 999999, "is_expertise": False}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_player_cannot_edit_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={"skill_proficiencies": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_skill_not_available_for_class_returns_400(
        self, client, player, player_token, db_session, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Fighter")
        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")
        await db_session.execute(
            class_available_skills.insert().values(class_id=character_class.id, skill_id=skill.id)
        )
        await db_session.commit()

        other_skill = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={"skill_proficiencies": [{"skill_id": other_skill.id, "is_expertise": False}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_too_many_skill_choices_returns_400(
        self, client, player, player_token, db_session, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        skill_a = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        skill_b = await create_skill(key="ACROBATICS", name="Acrobatics", ability="DEX")
        skill_c = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        await db_session.execute(
            class_available_skills.insert().values([
                {"class_id": character_class.id, "skill_id": skill_a.id},
                {"class_id": character_class.id, "skill_id": skill_b.id},
                {"class_id": character_class.id, "skill_id": skill_c.id},
            ])
        )
        await db_session.commit()

        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={
                "skill_proficiencies": [
                    {"skill_id": skill_a.id, "is_expertise": False},
                    {"skill_id": skill_b.id, "is_expertise": False},
                    {"skill_id": skill_c.id, "is_expertise": False},
                ]
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_happy_path_within_class_limit_succeeds(
        self, client, player, player_token, db_session, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        skill_a = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        skill_b = await create_skill(key="ACROBATICS", name="Acrobatics", ability="DEX")
        await db_session.execute(
            class_available_skills.insert().values([
                {"class_id": character_class.id, "skill_id": skill_a.id},
                {"class_id": character_class.id, "skill_id": skill_b.id},
            ])
        )
        await db_session.commit()

        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.put(
            f"/characters/{character.id}/skills",
            json={
                "skill_proficiencies": [
                    {"skill_id": skill_a.id, "is_expertise": False},
                    {"skill_id": skill_b.id, "is_expertise": True},
                ]
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        proficiencies = response.json()["skill_proficiencies"]
        assert len(proficiencies) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterSavingThrowProficiencies:
    async def test_replace_saving_throws(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.put(
            f"/characters/{character.id}/saving-throws",
            json={"saving_throws": ["STR", "CON"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        throws = response.json()["saving_throw_proficiencies"]
        assert {item["ability"] for item in throws} == {"STR", "CON"}

    async def test_clear_saving_throws(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        await client.put(
            f"/characters/{character.id}/saving-throws",
            json={"saving_throws": ["STR"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.put(
            f"/characters/{character.id}/saving-throws",
            json={"saving_throws": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["saving_throw_proficiencies"] == []
