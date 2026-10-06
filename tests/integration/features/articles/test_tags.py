"""Tests for PUT /articles/{id}/tags (full tag-set replacement)."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleTags:
    async def test_player_cannot_set_tags(self, client, create_article, player_token):
        article = await create_article(title="Khazad-dum")

        response = await client.put(
            f"/articles/{article['id']}/tags",
            json={"tag_ids": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_set_tags(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag_a = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        tag_b = (await client.post("/tags", json={"name": "Underground"}, headers=headers)).json()
        article = await create_article(title="Khazad-dum")

        response = await client.put(
            f"/articles/{article['id']}/tags",
            json={"tag_ids": [tag_a["id"], tag_b["id"]]},
            headers=headers,
        )

        assert response.status_code == 200
        tag_names = {t["name"] for t in response.json()["tags"]}
        assert tag_names == {"dwarven", "underground"}

    async def test_set_tags_replaces_previous_set(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag_a = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        tag_b = (await client.post("/tags", json={"name": "Underground"}, headers=headers)).json()
        article = await create_article(title="Khazad-dum", tag_ids=[tag_a["id"]])

        response = await client.put(
            f"/articles/{article['id']}/tags",
            json={"tag_ids": [tag_b["id"]]},
            headers=headers,
        )

        assert response.status_code == 200
        tag_names = {t["name"] for t in response.json()["tags"]}
        assert tag_names == {"underground"}

    async def test_set_tags_clears_all_tags(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        article = await create_article(title="Khazad-dum", tag_ids=[tag["id"]])

        response = await client.put(
            f"/articles/{article['id']}/tags",
            json={"tag_ids": []},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["tags"] == []

    async def test_set_tags_rejects_unknown_tag_id(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        article = await create_article(title="Khazad-dum")

        response = await client.put(
            f"/articles/{article['id']}/tags",
            json={"tag_ids": [999999]},
            headers=headers,
        )

        assert response.status_code == 400

    async def test_set_tags_rejects_duplicate_ids(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        article = await create_article(title="Khazad-dum")

        response = await client.put(
            f"/articles/{article['id']}/tags",
            json={"tag_ids": [tag["id"], tag["id"]]},
            headers=headers,
        )

        assert response.status_code == 422

    async def test_set_tags_for_missing_article_returns_404(self, client, gm_token):
        response = await client.put(
            "/articles/999999/tags",
            json={"tag_ids": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
