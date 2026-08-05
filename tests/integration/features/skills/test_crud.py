"""Tests for the skill write endpoints."""

import pytest


@pytest.mark.integration
class TestSkillCrud:
    def test_player_cannot_create_skill(self, client, player_token):
        response = client.post(
            "/skills/",
            json={"key": "CUSTOM", "name": "Custom", "ability": "STR"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_skill(self, client, gm_token):
        response = client.post(
            "/skills/",
            json={"key": "CUSTOM", "name": "Custom Skill", "ability": "STR"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["key"] == "CUSTOM"

    def test_create_duplicate_skill_key_returns_400(self, client, gm_token, create_skill):
        create_skill(key="STEALTH", name="Stealth", ability="DEX")
        response = client.post(
            "/skills/",
            json={"key": "STEALTH", "name": "Stealth", "ability": "DEX"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_update_skill(self, client, gm_token, create_skill):
        skill = create_skill(key="OLD_KEY", name="Old Name", ability="DEX")

        response = client.patch(
            f"/skills/{skill.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_gm_can_delete_skill(self, client, gm_token, create_skill):
        skill = create_skill(key="UNUSED", name="Unused", ability="DEX")

        response = client.delete(f"/skills/{skill.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/skills/{skill.id}").status_code == 404

    def test_delete_skill_in_use_by_race_returns_409(self, client, gm_token, create_skill, create_race):
        skill = create_skill(key="SURVIVAL", name="Survival", ability="WIS")
        race = create_race(name="Tracker")
        link_response = client.put(
            f"/races/{race.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert link_response.status_code == 200

        response = client.delete(f"/skills/{skill.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 409
