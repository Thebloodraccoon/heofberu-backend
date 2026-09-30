"""Tests for GET /articles/{id} and GET /articles/by-slug/{slug}: visibility and GM-block stripping."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleRead:
    async def test_uppercase_gm_block_stripped_for_anonymous(self, client, create_article):
        article = await create_article(
            body_markdown="Open part.\n\n:::GM\nThe villain is the mayor.\n:::\n\nTail.", status="published"
        )

        response = await client.get(f"/articles/{article['id']}")

        assert response.status_code == 200
        body = response.json()["body_markdown"]
        assert "mayor" not in body
        assert "Open part." in body and "Tail." in body

    async def test_uppercase_gm_block_kept_for_gm(self, client, create_article, gm_token):
        article = await create_article(body_markdown="Open part.\n\n:::GM\nThe villain is the mayor.\n:::")

        response = await client.get(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200
        assert "mayor" in response.json()["body_markdown"]

    async def test_response_has_no_view_count(self, client, create_article):
        article = await create_article(status="published")

        response = await client.get(f"/articles/{article['id']}")

        assert "view_count" not in response.json()
