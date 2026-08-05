"""Tests for the background write endpoints."""

import pytest


@pytest.mark.integration
class TestBackgroundCrud:
    def test_player_cannot_create_background(self, client, player_token):
        response = client.post(
            "/backgrounds/",
            json={"name": "Custom"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_background(self, client, gm_token):
        response = client.post(
            "/backgrounds/",
            json={"name": "Hermit"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Hermit"

    def test_create_duplicate_background_name_returns_400(self, client, gm_token, create_background):
        create_background(name="Acolyte")
        response = client.post(
            "/backgrounds/",
            json={"name": "Acolyte"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_set_granted_skills(self, client, gm_token, create_background, create_skill):
        background = create_background(name="Sage")
        skill = create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = client.put(
            f"/backgrounds/{background.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["granted_skills"]] == [skill.id]

    def test_gm_can_delete_background(self, client, gm_token, create_background):
        background = create_background(name="Doomed Background")

        response = client.delete(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/backgrounds/{background.id}").status_code == 404
