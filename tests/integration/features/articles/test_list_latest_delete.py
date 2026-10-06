"""Tests for GET /articles (incl. the status filter: latest / review queue) and DELETE /articles/{id}."""

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

    async def test_page_past_the_end_still_reports_the_total(self, client, create_article):
        for i in range(3):
            await create_article(title=f"Entry {i}", status="published")

        response = await client.get("/articles", params={"page": 5, "size": 2})

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleStatusFilter:
    async def test_latest_published_newest_first_excludes_drafts(self, client, create_article, gm_token):
        await create_article(title="Older", status="published")
        await create_article(title="Draft")
        await create_article(title="Newer", status="published")

        response = await client.get(
            "/articles",
            params={"status": "published", "sort": "newest"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["title"] for item in response.json()["items"]] == ["Newer", "Older"]

    async def test_published_filter_hides_gm_only_from_anonymous(self, client, create_article):
        await create_article(title="Public", status="published")
        await create_article(title="GM Only", status="published", visibility="gm_only")

        response = await client.get("/articles", params={"status": "published", "sort": "newest"})

        assert response.status_code == 200
        assert [item["title"] for item in response.json()["items"]] == ["Public"]

    async def test_review_queue_lists_only_in_review(self, client, create_article, founder_token):
        await create_article(title="Queued", status="in_review")
        await create_article(title="Draft")
        await create_article(title="Live", status="published")

        response = await client.get(
            "/articles", params={"status": "in_review"}, headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 200
        assert [item["title"] for item in response.json()["items"]] == ["Queued"]

    async def test_review_queue_is_empty_for_anonymous(self, client, create_article):
        await create_article(title="Queued", status="in_review")

        response = await client.get("/articles", params={"status": "in_review"})

        assert response.status_code == 200
        assert response.json()["total"] == 0


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

        response = await client.delete(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403

    async def test_founder_can_delete_article(self, client, create_article, founder_token):
        article = await create_article(title="Khazad-dum")

        response = await client.delete(
            f"/articles/{article['id']}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 204

        fetched = await client.get(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {founder_token}"})
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
        response = await client.delete("/articles/999999", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleCursorPagination:
    @pytest.mark.parametrize("sort", ["title", "newest", "oldest", "updated"])
    async def test_cursor_walk_matches_offset_order_for_every_sort(self, client, create_article, sort):
        for title in ("Delta", "Alpha", "Charlie", "Bravo", "Echo"):
            await create_article(title=title, status="published")

        offset = (await client.get("/articles", params={"sort": sort, "size": 10})).json()["items"]

        ids, cursor = [], None
        while True:
            params = {"pagination": "cursor", "size": 2, "sort": sort, **({"cursor": cursor} if cursor else {})}
            body = (await client.get("/articles", params=params)).json()
            assert set(body) == {"items", "next_cursor", "size"}
            ids.extend(item["id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert ids == [item["id"] for item in offset]

    async def test_cursor_keeps_visibility_rules(self, client, create_article):
        await create_article(title="Public", status="published")
        await create_article(title="Draft")

        body = (await client.get("/articles", params={"pagination": "cursor"})).json()

        assert [item["title"] for item in body["items"]] == ["Public"]

    async def test_cursor_from_another_sort_is_rejected(self, client, create_article):
        for title in ("A", "B", "C"):
            await create_article(title=title, status="published")
        cursor = (await client.get("/articles", params={"pagination": "cursor", "size": 1})).json()["next_cursor"]

        response = await client.get("/articles", params={"cursor": cursor, "sort": "newest"})

        assert response.status_code == 422

    @pytest.mark.parametrize("cursor", ["garbage!", "e30", "x" * 600])
    async def test_invalid_cursor_is_rejected(self, client, cursor):
        assert (await client.get("/articles", params={"cursor": cursor})).status_code == 422
