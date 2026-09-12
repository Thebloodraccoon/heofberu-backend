"""Background suggestion pool endpoints: GET/PUT /backgrounds/{id}/suggestions."""

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
class TestSetBackgroundSuggestions:
    async def test_gm_can_replace_suggestions(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)

        response = await client.put(
            f"/backgrounds/{background.id}/suggestions",
            json={
                "suggestions": [
                    {"suggestion_type": "PERSONALITY_TRAIT", "text": "I feel far more comfortable around animals."},
                    {"suggestion_type": "IDEAL", "text": "Change. Life is like the seasons, in constant change."},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert {item["suggestion_type"] for item in body} == {"PERSONALITY_TRAIT", "IDEAL"}

        listed = await client.get(f"/backgrounds/{background.id}/suggestions")
        assert len(listed.json()) == 2

    async def test_put_is_a_full_replace_not_a_merge(self, client, gm_token, create_background):
        background = await create_background(name="Outlander", with_suggestions=False)

        first = await client.put(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestions": [{"suggestion_type": "BOND", "text": "An injury I received was caused by cruelty."}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert first.status_code == 200
        assert len(first.json()) == 1

        second = await client.put(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestions": [{"suggestion_type": "FLAW", "text": "I am too enamored of ale."}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert second.status_code == 200
        assert len(second.json()) == 1
        assert second.json()[0]["suggestion_type"] == "FLAW"

    async def test_gm_can_clear_all_suggestions(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestions": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_set_for_missing_background_returns_404(self, client, gm_token):
        response = await client.put(
            "/backgrounds/99999/suggestions",
            json={"suggestions": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_replace_suggestions(self, client, player_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestions": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_rejects_empty_text(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/suggestions",
            json={"suggestions": [{"suggestion_type": "IDEAL", "text": ""}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422
