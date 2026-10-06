"""Background suggestion pool endpoints: GET /suggestions, POST/PATCH/DELETE /suggestions/{id}."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestListBackgroundSuggestions:
    async def test_list_returns_empty_for_a_background_with_none(self, client, create_background):
        background = await create_background(name="Hermit", with_suggestions=False)

        response = await client.get(f"/backgrounds/{background.id}/suggestions")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_returns_seeded_suggestions(self, client, create_background):
        background = await create_background(name="Sage")

        response = await client.get(f"/backgrounds/{background.id}/suggestions")

        assert response.status_code == 200
        types = {item["suggestion_type"] for item in response.json()}
        assert types == {"PERSONALITY_TRAIT", "IDEAL", "BOND", "FLAW"}

    async def test_list_for_missing_background_returns_404(self, client):
        response = await client.get("/backgrounds/99999/suggestions")

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreateBackgroundSuggestion:
    async def test_gm_can_add_a_suggestion(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)

        response = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "PERSONALITY_TRAIT", "text": "I feel far more comfortable around animals."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["suggestion_type"] == "PERSONALITY_TRAIT"
        assert body["text"] == "I feel far more comfortable around animals."

        listed = await client.get(f"/backgrounds/{background.id}/suggestions")
        assert len(listed.json()) == 1

    async def test_add_appends_without_removing_existing(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)

        first = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "BOND", "text": "An injury I received was caused by cruelty."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert first.status_code == 201

        second = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "FLAW", "text": "I am too enamored of ale."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert second.status_code == 201

        listed = await client.get(f"/backgrounds/{background.id}/suggestions")
        assert {item["suggestion_type"] for item in listed.json()} == {"BOND", "FLAW"}

    async def test_create_for_missing_background_returns_404(self, client, gm_token):
        response = await client.post(
            "/backgrounds/99999/suggestions",
            json={"suggestion_type": "IDEAL", "text": "Some ideal."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_add_a_suggestion(self, client, player_token, create_background):
        background = await create_background(name="Sage")

        response = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "IDEAL", "text": "Some ideal."},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_rejects_empty_text(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "IDEAL", "text": ""},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestUpdateBackgroundSuggestion:
    async def test_gm_can_update_text(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)
        created = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "IDEAL", "text": "Original text."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        suggestion_id = created.json()["id"]

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/{suggestion_id}",
            json={"text": "Change. Life is like the seasons, in constant change."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == suggestion_id
        assert body["suggestion_type"] == "IDEAL"
        assert body["text"] == "Change. Life is like the seasons, in constant change."

    async def test_omitted_fields_are_left_as_is(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)
        created = await client.post(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestion_type": "BOND", "text": "Original text."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        suggestion_id = created.json()["id"]

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/{suggestion_id}",
            json={"text": "Updated text."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["suggestion_type"] == "BOND"

    async def test_update_for_missing_suggestion_returns_404(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/99999",
            json={"text": "Updated text."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_update_for_missing_background_returns_404(self, client, gm_token):
        response = await client.patch(
            "/backgrounds/99999/suggestions/1",
            json={"text": "Updated text."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_update_a_suggestion(self, client, player_token, gm_token, create_background):
        background = await create_background(name="Sage")
        existing = await client.get(f"/backgrounds/{background.id}/suggestions")
        suggestion_id = existing.json()[0]["id"]

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/{suggestion_id}",
            json={"text": "Updated text."},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_rejects_empty_text(self, client, gm_token, create_background):
        background = await create_background(name="Sage")
        existing = await client.get(f"/backgrounds/{background.id}/suggestions")
        suggestion_id = existing.json()[0]["id"]

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/{suggestion_id}",
            json={"text": ""},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteBackgroundSuggestion:
    async def test_gm_can_delete_a_suggestion(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)
        ids = []
        for text in ("I am too enamored of ale.", "I never trust a stranger."):
            created = await client.post(
                f"/backgrounds/{background.id}/suggestions",
                json={"suggestion_type": "FLAW", "text": text},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            ids.append(created.json()["id"])

        response = await client.delete(
            f"/backgrounds/{background.id}/suggestions/{ids[0]}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204

        listed = await client.get(f"/backgrounds/{background.id}/suggestions")
        assert [item["id"] for item in listed.json()] == [ids[1]]

    async def test_delete_for_missing_suggestion_returns_404(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.delete(
            f"/backgrounds/{background.id}/suggestions/99999",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_delete_for_missing_background_returns_404(self, client, gm_token):
        response = await client.delete(
            "/backgrounds/99999/suggestions/1",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_delete_a_suggestion(self, client, player_token, create_background):
        background = await create_background(name="Sage")
        existing = await client.get(f"/backgrounds/{background.id}/suggestions")
        suggestion_id = existing.json()[0]["id"]

        response = await client.delete(
            f"/backgrounds/{background.id}/suggestions/{suggestion_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
