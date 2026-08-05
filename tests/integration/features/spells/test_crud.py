"""Tests for the spell write endpoints."""

import pytest

SPELL_PAYLOAD = {
    "name": "Magic Missile",
    "school": "EVOCATION",
    "level": "LEVEL_1",
    "cast_time": "ACTION",
    "range_type": "RANGED",
    "range_value": 120,
    "components": ["VERBAL", "SOMATIC"],
    "is_material_consumed": False,
    "duration": "INSTANTANEOUS",
    "description": "You create three glowing darts of magical force.",
}


@pytest.mark.integration
class TestSpellCrud:
    def test_player_cannot_create_spell(self, client, player_token):
        response = client.post(
            "/spells/",
            json=SPELL_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_spell(self, client, gm_token):
        response = client.post("/spells/", json=SPELL_PAYLOAD, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 201
        assert response.json()["name"] == "Magic Missile"
        assert response.json()["level"] == "LEVEL_1"

    def test_create_duplicate_spell_name_returns_400(self, client, gm_token, create_spell):
        create_spell(name="Magic Missile")
        response = client.post("/spells/", json=SPELL_PAYLOAD, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 400

    def test_gm_can_update_spell(self, client, gm_token, create_spell):
        spell = create_spell(name="Old Spell Name")

        response = client.patch(
            f"/spells/{spell.id}", json={"name": "New Spell Name"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Spell Name"

    def test_gm_can_set_available_classes_and_races(self, client, gm_token, create_spell, create_class, create_race):
        spell = create_spell(name="Restricted Spell")
        character_class = create_class(name="Sorcerer", hit_dice="D6", spellcasting_ability="CHA")
        race = create_race(name="High Elf")

        classes_response = client.put(
            f"/spells/{spell.id}/classes",
            json={"class_ids": [character_class.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert classes_response.status_code == 200
        assert [item["id"] for item in classes_response.json()["available_classes"]] == [character_class.id]

        races_response = client.put(
            f"/spells/{spell.id}/races",
            json={"race_ids": [race.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert races_response.status_code == 200
        assert [item["id"] for item in races_response.json()["available_races"]] == [race.id]

    def test_gm_can_delete_spell(self, client, gm_token, create_spell):
        spell = create_spell(name="Doomed Spell")

        response = client.delete(f"/spells/{spell.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/spells/{spell.id}").status_code == 404
