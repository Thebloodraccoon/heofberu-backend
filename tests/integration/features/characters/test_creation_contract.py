"""Tests for the one-shot character-creation contract (level 1, skills, starting HP, class saves)."""

import pytest

from app.models.class_association_models import class_available_skills


async def set_available_skills(db_session, character_class, *skills):
    """Attach skills to a class's available_skills via the association table."""

    await db_session.execute(
        class_available_skills.insert().values(
            [{"class_id": character_class.id, "skill_id": skill.id} for skill in skills]
        )
    )
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreationSkillChoices:
    async def test_chosen_skills_are_written_with_is_expertise_false(
        self,
        client,
        player,
        player_token,
        db_session,
        create_class,
        create_skill,
    ):
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        skill_a = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        skill_b = await create_skill(key="ACROBATICS", name="Acrobatics", ability="DEX")
        await set_available_skills(db_session, character_class, skill_a, skill_b)

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "skill_ids": [skill_a.id, skill_b.id],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        proficiencies = response.json()["skill_proficiencies"]
        assert {item["skill_id"] for item in proficiencies} == {skill_a.id, skill_b.id}
        assert all(item["is_expertise"] is False for item in proficiencies)

    async def test_skill_outside_class_available_skills_returns_400(
        self,
        client,
        player,
        player_token,
        db_session,
        create_class,
        create_skill,
    ):
        character_class = await create_class(name="Fighter")
        available = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        other = await create_skill(key="ARCANA", name="Arcana", ability="INT")
        await set_available_skills(db_session, character_class, available)

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "skill_ids": [other.id],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_unknown_skill_id_returns_400(self, client, player, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "skill_ids": [999999],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_too_many_skill_choices_returns_400(
        self,
        client,
        player,
        player_token,
        db_session,
        create_class,
        create_skill,
    ):
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        skill_a = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        skill_b = await create_skill(key="ACROBATICS", name="Acrobatics", ability="DEX")
        skill_c = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        await set_available_skills(db_session, character_class, skill_a, skill_b, skill_c)

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "skill_ids": [skill_a.id, skill_b.id, skill_c.id],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_duplicate_skill_ids_return_422(self, client, player, player_token, create_class, create_skill):
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        skill = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "skill_ids": [skill.id, skill.id],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreationBackgroundSkills:
    async def test_background_skills_added_and_merged_with_choices(
        self,
        client,
        gm_token,
        player,
        player_token,
        db_session,
        create_class,
        create_skill,
        create_background,
    ):
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        chosen = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        granted = await create_skill(key="RELIGION", name="Religion", ability="INT")
        await set_available_skills(db_session, character_class, chosen)
        background = await create_background(name="Acolyte")
        put_response = await client.put(
            f"/backgrounds/{background.id}/skills",
            json={"skill_ids": [granted.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert put_response.status_code == 200, put_response.text

        response = await client.post(
            "/characters",
            json={
                "name": "Acolyte",
                "class_id": character_class.id,
                "background_id": background.id,
                "skill_ids": [chosen.id],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        proficiencies = response.json()["skill_proficiencies"]
        assert {item["skill_id"] for item in proficiencies} == {chosen.id, granted.id}
        assert len(proficiencies) == 2

    async def test_background_only_skills_written_without_choices(
        self,
        client,
        gm_token,
        player,
        player_token,
        create_class,
        create_skill,
        create_background,
    ):
        character_class = await create_class(name="Fighter")
        skill = await create_skill(key="RELIGION", name="Religion", ability="INT")
        background = await create_background(name="Acolyte")
        put_response = await client.put(
            f"/backgrounds/{background.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert put_response.status_code == 200, put_response.text

        response = await client.post(
            "/characters",
            json={
                "name": "Acolyte",
                "class_id": character_class.id,
                "background_id": background.id,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        proficiencies = response.json()["skill_proficiencies"]
        assert {item["skill_id"] for item in proficiencies} == {skill.id}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreationHp:
    async def test_default_max_hp_is_hit_die_plus_con_modifier(self, client, player, player_token, create_class):
        # Fighter D10 with base CON 12 -> CON mod +1 -> default max_hp 11.
        character_class = await create_class(name="Fighter", hit_dice="D10")

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "constitution": 12,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["max_hp"] == 11
        assert body["current_hp"] == 11
        assert body["temp_hp"] == 0

    async def test_explicit_max_hp_is_rejected(self, client, player, player_token, create_class):
        """HP is fully server-derived at level 1 — sending `max_hp` fails with a 422."""
        character_class = await create_class(name="Fighter", hit_dice="D10")

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "max_hp": 4,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_client_sent_level_is_rejected(self, client, player, player_token, create_class):
        """`extra="forbid"` — unknown fields like `level` are rejected with a 422."""
        character_class = await create_class(name="Fighter", hit_dice="D10")

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
                "level": 5,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreationSavingThrows:
    async def test_saving_throws_come_from_the_class(self, client, gm_token, player_token, create_class):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        put_response = await client.put(
            f"/classes/{character_class.id}/saving-throws",
            json={"saving_throws": ["STR", "CON"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert put_response.status_code == 200, put_response.text

        response = await client.post(
            "/characters",
            json={
                "name": "Conan",
                "class_id": character_class.id,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        throws = response.json()["saving_throw_proficiencies"]
        assert {item["ability"] for item in throws} == {"STR", "CON"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreationRaceSkills:
    async def test_race_granted_skills_written_without_choices(
        self,
        client,
        gm_token,
        player,
        player_token,
        create_class,
        create_skill,
        create_race,
    ):
        character_class = await create_class(name="Fighter")
        skill = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")
        race = await create_race(name="Elf")
        put_response = await client.put(
            f"/races/{race.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert put_response.status_code == 200, put_response.text

        response = await client.post(
            "/characters",
            json={
                "name": "Legolas",
                "class_id": character_class.id,
                "race_id": race.id,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        proficiencies = response.json()["skill_proficiencies"]
        assert {item["skill_id"] for item in proficiencies} == {skill.id}
        assert all(item["is_expertise"] is False for item in proficiencies)

    async def test_race_choice_and_background_skills_merge_with_dedupe(
        self,
        client,
        gm_token,
        player,
        player_token,
        db_session,
        create_class,
        create_skill,
        create_background,
        create_race,
    ):
        """Skills granted by several sources (choice + race) produce a single row."""
        character_class = await create_class(name="Fighter", skill_choice_count=2)
        chosen = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        granted = await create_skill(key="RELIGION", name="Religion", ability="INT")
        racial = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")
        await set_available_skills(db_session, character_class, chosen)

        background = await create_background(name="Acolyte")
        put_bg = await client.put(
            f"/backgrounds/{background.id}/skills",
            json={"skill_ids": [granted.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert put_bg.status_code == 200, put_bg.text

        race = await create_race(name="Elf")
        put_race = await client.put(
            f"/races/{race.id}/skills",
            json={"skill_ids": [chosen.id, racial.id]},  # `chosen` overlaps with the class choice
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert put_race.status_code == 200, put_race.text

        response = await client.post(
            "/characters",
            json={
                "name": "Acolyte",
                "class_id": character_class.id,
                "race_id": race.id,
                "background_id": background.id,
                "skill_ids": [chosen.id],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        proficiencies = response.json()["skill_proficiencies"]
        assert {item["skill_id"] for item in proficiencies} == {chosen.id, granted.id, racial.id}
        assert len(proficiencies) == 3
