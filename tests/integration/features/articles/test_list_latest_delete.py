"""Tests for GET /articles, GET /articles/latest, and DELETE /articles/{id}."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleList:
    async def test_list_hides_drafts_and_gm_only_from_anonymous(self, client, create_article):
        await create_article(title="Published Public", status="published")
        await create_article(title="Draft One")
        await create_article(title="Published GM Only", status="published", visibility="gm_only")

        response = await client.get("/articles")

        assert response.status_code == 200
        body = response.json()
        assert [item["title"] for item in body["items"]] == ["Published Public"]

    async def test_list_shows_everything_to_gm(self, client, create_article, gm_token):
        await create_article(title="Published Public", status="published")
        await create_article(title="Draft One")

        response = await client.get("/articles", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200
        assert response.json()["total"] == 2

    async def test_list_filters_by_article_type(self, client, create_article):
        await create_article(title="A Deity", article_type="deity", status="published")
        await create_article(title="An Artifact", article_type="artifact", status="published")

        response = await client.get("/articles", params={"article_type": "deity"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["article_type"] == "deity"

    async def test_list_filters_by_search_substring(self, client, create_article):
        await create_article(title="Khazad-dum", status="published")
        await create_article(title="Moria Region", status="published")

        response = await client.get("/articles", params={"search": "khazad"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Khazad-dum"

    async def test_list_filters_by_tag(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Border Region"}, headers=headers)).json()

        tagged = await create_article(title="Tagged Article", status="published", tag_ids=[tag["id"]])
        await create_article(title="Untagged Article", status="published")

        response = await client.get("/articles", params={"tag_id": tag["id"]})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == tagged["id"]

    async def test_list_paginates(self, client, create_article):
        for i in range(3):
            await create_article(title=f"Entry {i}", status="published")

        response = await client.get("/articles", params={"page": 1, "size": 2, "sort": "title"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleLatest:
    async def test_latest_excludes_drafts(self, client, create_article):
        await create_article(title="Published", status="published")
        await create_article(title="Draft")

        response = await client.get("/articles/latest")

        assert response.status_code == 200
        titles = [item["title"] for item in response.json()]
        assert titles == ["Published"]

    async def test_latest_hides_gm_only_from_anonymous(self, client, create_article):
        await create_article(title="Public", status="published")
        await create_article(title="GM Only", status="published", visibility="gm_only")

        response = await client.get("/articles/latest")

        assert response.status_code == 200
        titles = [item["title"] for item in response.json()]
        assert titles == ["Public"]

    async def test_latest_respects_limit(self, client, create_article):
        for i in range(3):
            await create_article(title=f"Entry {i}", status="published")

        response = await client.get("/articles/latest", params={"limit": 2})

        assert response.status_code == 200
        assert len(response.json()) == 2

    async def test_latest_filters_by_article_type(self, client, create_article):
        await create_article(title="A Deity", article_type="deity", status="published")
        await create_article(title="An Artifact", article_type="artifact", status="published")

        response = await client.get("/articles/latest", params={"article_type": "deity"})

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["article_type"] == "deity"


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleDelete:
    async def test_player_cannot_delete_article(self, client, create_article, player_token):
        article = await create_article(title="Khazad-dum")

        response = await client.delete(
            f"/articles/{article['id']}", headers={"Authorization": f"Bearer {player_token}"}
        )

        assert response.status_code == 403

    async def test_gm_cannot_delete_article(self, client, create_article, gm_token):
        article = await create_article(title="Khazad-dum")

        response = await client.delete(
            f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 403

    async def test_founder_can_delete_article(self, client, create_article, founder_token):
        article = await create_article(title="Khazad-dum")

        response = await client.delete(
            f"/articles/{article['id']}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 204

        fetched = await client.get(
            f"/articles/{article['id']}", headers={"Authorization": f"Bearer {founder_token}"}
        )
        assert fetched.status_code == 404

    async def test_delete_detaches_children_instead_of_blocking(self, client, create_article, founder_token, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        parent = await create_article(title="Moria Region", article_type="region")
        child = await create_article(title="Khazad-dum City", article_type="location", parent_id=parent["id"])

        response = await client.delete(
            f"/articles/{parent['id']}", headers={"Authorization": f"Bearer {founder_token}"}
        )
        assert response.status_code == 204

        fetched_child = await client.get(f"/articles/{child['id']}", headers=headers)
        assert fetched_child.status_code == 200
        assert fetched_child.json()["parent_id"] is None

    async def test_delete_missing_article_returns_404(self, client, founder_token):
        response = await client.delete(
            "/articles/999999", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 404
