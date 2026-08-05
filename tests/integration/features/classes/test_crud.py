"""Tests for the class write endpoints."""

import pytest


@pytest.mark.integration
class TestClassCrud:
    def test_player_cannot_create_class(self, client, player_token):
        response = client.post(
            "/classes/",
            json={"name": "Homebrew", "hit_dice": "D8", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_non_caster_class(self, client, gm_token):
        response = client.post(
            "/classes/",
            json={"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Fighter"
        assert body["spellcasting_ability"] is None

    def test_gm_can_create_caster_class(self, client, gm_token, create_skill):
        skill = create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = client.post(
            "/classes/",
            json={
                "name": "Wizard",
                "hit_dice": "D6",
                "spellcasting_ability": "INT",
                "primary_abilities": ["INT"],
                "saving_throws": ["INT", "WIS"],
                "available_skills": [skill.id],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["spellcasting_ability"] == "INT"
        assert body["primary_abilities"] == [{"ability": "INT"}]
        assert body["saving_throws"] == [{"ability": "INT"}, {"ability": "WIS"}]
        assert [item["id"] for item in body["available_skills"]] == [skill.id]

    def test_create_class_spellcasting_ability_not_primary_returns_400(self, client, gm_token):
        response = client.post(
            "/classes/",
            json={"name": "Bad Caster", "hit_dice": "D8", "spellcasting_ability": "CHA"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    def test_create_duplicate_class_name_returns_400(self, client, gm_token, create_class):
        create_class(name="Fighter")
        response = client.post(
            "/classes/",
            json={"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_update_class(self, client, gm_token, create_class):
        character_class = create_class(name="Old Name")

        response = client.patch(
            f"/classes/{character_class.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_update_primary_abilities_dropping_spellcasting_ability_returns_400(self, client, gm_token, create_class):
        character_class = create_class(name="Wizard", spellcasting_ability="INT")

        response = client.patch(
            f"/classes/{character_class.id}",
            json={"primary_abilities": ["WIS"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_replace_saving_throws(self, client, gm_token, create_class):
        character_class = create_class(name="Dexy")

        response = client.put(
            f"/classes/{character_class.id}/saving-throws",
            json={"saving_throws": ["DEX", "INT"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {item["ability"] for item in response.json()["saving_throws"]} == {"DEX", "INT"}

    def test_gm_can_set_available_skills(self, client, gm_token, create_class, create_skill):
        character_class = create_class(name="Skillful")
        skill = create_skill(key="PERSUASION", name="Persuasion", ability="CHA")

        response = client.put(
            f"/classes/{character_class.id}/available-skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["available_skills"]] == [skill.id]

    def test_gm_can_set_spell_slots(self, client, gm_token, create_class):
        character_class = create_class(name="Wizard", spellcasting_ability="INT")

        response = client.put(
            f"/classes/{character_class.id}/spell-slots/1",
            json={"slots": [{"spell_level": "LEVEL_1", "slots": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200

    def test_set_spell_slots_invalid_level_returns_400(self, client, gm_token, create_class):
        character_class = create_class(name="Wizard", spellcasting_ability="INT")

        response = client.put(
            f"/classes/{character_class.id}/spell-slots/21",
            json={"slots": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_delete_class(self, client, gm_token, create_class):
        character_class = create_class(name="Doomed Class")

        response = client.delete(f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/classes/{character_class.id}").status_code == 404

    def test_delete_class_in_use_by_character_returns_409(
        self, client, gm_token, create_class, create_user, create_character
    ):
        character_class = create_class(name="Popular Class")
        player = create_user()
        create_character(owner_id=player.id, class_id=character_class.id)

        response = client.delete(f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 409
