"""
End-to-end seeding of the class catalog: POST /classes atomically seeds the
directly-owned child rows (saving throws, armor/weapon proficiencies,
available skills), while the heavier nested rows (spell-slot progression
including a CANTRIP row, features) are attached through their dedicated
endpoints — and GET /classes/{id} then embeds the whole picture.
"""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestClassCreationSeeding:
    async def test_create_class_seeds_throws_proficiencies_and_skills(self, client, gm_token, create_skill):
        skill_a = await create_skill(key="ARCANA", name="Arcana", ability="INT")
        skill_b = await create_skill(key="HISTORY", name="History", ability="INT")

        response = await client.post(
            "/classes",
            json={
                "name": "Seeded Wizard",
                "hit_dice": "D6",
                "spellcasting_ability": "INT",
                "saving_throws": ["INT", "WIS"],
                "weapon_proficiencies": ["SIMPLE"],
                "available_skills": [skill_a.id, skill_b.id],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert {item["ability"] for item in body["saving_throws"]} == {"INT", "WIS"}
        assert body["armor_proficiencies"] == []
        assert [item["weapon_category"] for item in body["weapon_proficiencies"]] == ["SIMPLE"]
        assert sorted(item["id"] for item in body["available_skills"]) == sorted([skill_a.id, skill_b.id])

    async def test_seeded_rows_survive_a_fresh_full_read(self, client, gm_token, create_skill):
        """GET /classes/{id} re-embeds everything POST /classes seeded."""
        skill = await create_skill(key="RELIGION", name="Religion", ability="WIS")

        created = await client.post(
            "/classes",
            json={
                "name": "Seeded Cleric",
                "hit_dice": "D8",
                "spellcasting_ability": "WIS",
                "saving_throws": ["WIS", "CHA"],
                "armor_proficiencies": ["LIGHT", "MEDIUM", "SHIELD"],
                "weapon_proficiencies": ["SIMPLE"],
                "available_skills": [skill.id],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        class_id = created.json()["id"]

        fetched_response = await client.get(f"/classes/{class_id}")
        assert fetched_response.status_code == 200
        fetched = fetched_response.json()
        assert fetched["name"] == "Seeded Cleric"
        assert {item["ability"] for item in fetched["saving_throws"]} == {"WIS", "CHA"}
        assert [item["armor_type"] for item in fetched["armor_proficiencies"]] == ["LIGHT", "MEDIUM", "SHIELD"]
        assert [item["weapon_category"] for item in fetched["weapon_proficiencies"]] == ["SIMPLE"]
        assert [item["id"] for item in fetched["available_skills"]] == [skill.id]

    async def test_create_class_rejects_duplicate_nested_entries(self, client, gm_token):
        response = await client.post(
            "/classes",
            json={
                "name": "Duplicationist",
                "hit_dice": "D8",
                "spellcasting_ability": None,
                "saving_throws": ["STR", "STR"],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_create_class_with_unknown_available_skill_returns_400(self, client, gm_token):
        response = await client.post(
            "/classes",
            json={
                "name": "Ghost Skills",
                "hit_dice": "D8",
                "spellcasting_ability": None,
                "available_skills": [999999],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullCatalogPicture:
    async def test_spell_slot_progression_and_features_embed_in_full_read(self, client, gm_token):
        created = await client.post(
            "/classes",
            json={"name": "Full Picture Sorcerer", "hit_dice": "D6", "spellcasting_ability": "CHA"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        character_class_id = created.json()["id"]
        assert created.json()["spell_slot_progression"] == []

        slots_response = await client.put(
            f"/classes/{character_class_id}/spell-slots",
            params={"class_level": 1},
            json={"slots": [{"spell_level": "CANTRIP", "slots": 4}, {"spell_level": "LEVEL_1", "slots": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert slots_response.status_code == 200

        feature_response = await client.post(
            "/features",
            json={
                "name": "Font of Magic",
                "level": 1,
                "description": "Metamagic fuel.",
                "source_type": "CLASS",
                "class_id": character_class_id,
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert feature_response.status_code == 201

        subclass_response = await client.post(
            "/subclasses",
            json={"name": "Draconic Bloodline", "class_id": character_class_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert subclass_response.status_code == 201

        fetched_response = await client.get(f"/classes/{character_class_id}")
        assert fetched_response.status_code == 200
        fetched = fetched_response.json()
        assert {(row["spell_level"], row["slots"]) for row in fetched["spell_slot_progression"]} == {
            ("CANTRIP", 4),
            ("LEVEL_1", 2),
        }
        assert [feature["name"] for feature in fetched["features"]] == ["Font of Magic"]
        assert [{"id": subclass["id"], "name": subclass["name"]} for subclass in fetched["subclasses"]] == [
            {"id": subclass_response.json()["id"], "name": "Draconic Bloodline"}
        ]

    async def test_seeded_slots_flow_into_new_characters_at_creation(self, client, gm_token, player, login_as):
        """A character of the freshly seeded caster class starts with the CANTRIP/LEVEL_1 totals."""
        created = await client.post(
            "/classes",
            json={"name": "Flow Warlock", "hit_dice": "D8", "spellcasting_ability": "CHA"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        character_class_id = created.json()["id"]

        slots_response = await client.put(
            f"/classes/{character_class_id}/spell-slots",
            params={"class_level": 1},
            json={"slots": [{"spell_level": "CANTRIP", "slots": 2}, {"spell_level": "LEVEL_1", "slots": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert slots_response.status_code == 200

        token = await login_as(player)
        char_response = await client.post(
            "/characters",
            json={"name": "Slot Flow", "class_id": character_class_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert char_response.status_code == 201, char_response.text
        character = char_response.json()

        spells_response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert spells_response.status_code == 200
        assert {slot["spell_level"]: slot["total"] for slot in spells_response.json()["spell_slots"]} == {
            "CANTRIP": 2,
            "LEVEL_1": 1,
        }
