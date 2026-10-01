"""Integration tests: creating a background auto-seeds 4 default placeholder suggestions."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackgroundSuggestionSeeding:
    async def test_creating_background_seeds_four_default_suggestions(self, client, gm_token):
        response = await client.post(
            "/backgrounds",
            json={"name": "Seeded Hermit"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert {(row["suggestion_type"], row["text"]) for row in body["suggestions"]} == {
            ("PERSONALITY_TRAIT", "-"),
            ("IDEAL", "-"),
            ("BOND", "-"),
            ("FLAW", "-"),
        }

        suggestions = await client.get(f"/backgrounds/{body['id']}/suggestions")

        assert suggestions.status_code == 200
        rows = suggestions.json()
        assert len(rows) == 4
        assert {(row["suggestion_type"], row["text"]) for row in rows} == {
            ("PERSONALITY_TRAIT", "-"),
            ("IDEAL", "-"),
            ("BOND", "-"),
            ("FLAW", "-"),
        }

    async def test_creating_background_embedds_seeded_suggestions_in_detail_get(self, client, gm_token):
        response = await client.post(
            "/backgrounds",
            json={"name": "Seeded Sage"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        background_id = response.json()["id"]

        detail = await client.get(f"/backgrounds/{background_id}")

        assert detail.status_code == 200
        embedded = detail.json()["suggestions"]
        assert len(embedded) == 4
        assert {(row["suggestion_type"], row["text"]) for row in embedded} == {
            ("PERSONALITY_TRAIT", "-"),
            ("IDEAL", "-"),
            ("BOND", "-"),
            ("FLAW", "-"),
        }
