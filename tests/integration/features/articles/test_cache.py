"""Article cache: exact-key invalidation after commit, namespace purge on tag/subtype renames."""

import pytest

from app.features.articles.cache import article_cache_key
from app.settings import settings


@pytest.fixture
def caching_on(monkeypatch, redis_client):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 300)


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleCache:
    async def test_read_populates_exactly_the_key_the_invalidator_targets(
        self, client, create_article, caching_on, redis_client
    ):
        article = await create_article(title="Khazad-dum", status="published")

        await client.get(f"/articles/{article['id']}")

        assert await redis_client.exists(article_cache_key(article["id"])) == 1

    async def test_update_drops_only_that_article_and_serves_fresh_data(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        edited = await create_article(title="Khazad-dum", status="published")
        other = await create_article(title="Moria", status="published")
        await client.get(f"/articles/{edited['id']}")
        await client.get(f"/articles/{other['id']}")

        await client.patch(
            f"/articles/{edited['id']}",
            json={"body_markdown": "new text"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert await redis_client.exists(article_cache_key(edited["id"])) == 0
        assert await redis_client.exists(article_cache_key(other["id"])) == 1
        assert (await client.get(f"/articles/{edited['id']}")).json()["body_markdown"] == "new text"

    async def test_failed_update_keeps_the_cached_payload(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        article = await create_article(title="Khazad-dum", status="published")
        await client.get(f"/articles/{article['id']}")

        response = await client.patch(
            f"/articles/{article['id']}", json={"parent_id": 999999}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 400
        assert await redis_client.exists(article_cache_key(article["id"])) == 1

    async def test_transition_refreshes_the_cached_status(
        self, client, create_article, founder_token, caching_on, redis_client
    ):
        article = await create_article(title="Khazad-dum", status="published")
        await client.get(f"/articles/{article['id']}")

        await client.post(f"/articles/{article['id']}/archive", headers={"Authorization": f"Bearer {founder_token}"})

        assert (await client.get(f"/articles/{article['id']}")).status_code == 404

    async def test_delete_drops_the_article_and_its_children_payloads(
        self, client, create_article, founder_token, caching_on, redis_client
    ):
        parent = await create_article(title="Parent", status="published")
        child = await create_article(title="Child", status="published", parent_id=parent["id"])
        untouched = await create_article(title="Untouched", status="published")
        for article in (parent, child, untouched):
            await client.get(f"/articles/{article['id']}")
        assert (await client.get(f"/articles/{child['id']}")).json()["parent_id"] == parent["id"]

        await client.delete(f"/articles/{parent['id']}", headers={"Authorization": f"Bearer {founder_token}"})

        assert await redis_client.exists(article_cache_key(parent["id"])) == 0
        assert await redis_client.exists(article_cache_key(child["id"])) == 0
        assert await redis_client.exists(article_cache_key(untouched["id"])) == 1
        assert (await client.get(f"/articles/{child['id']}")).json()["parent_id"] is None

    async def test_set_tags_drops_the_article_payload(self, client, create_article, gm_token, caching_on, redis_client):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        article = await create_article(title="Khazad-dum", status="published")
        await client.get(f"/articles/{article['id']}")

        await client.put(f"/articles/{article['id']}/tags", json={"tag_ids": [tag["id"]]}, headers=headers)

        assert [t["name"] for t in (await client.get(f"/articles/{article['id']}")).json()["tags"]] == ["dwarven"]

    async def test_tag_rename_refreshes_cached_articles(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        article = await create_article(title="Khazad-dum", status="published", tag_ids=[tag["id"]])
        await client.get(f"/articles/{article['id']}")

        await client.patch(f"/tags/{tag['id']}", json={"name": "Dwarrow"}, headers=headers)

        assert [t["name"] for t in (await client.get(f"/articles/{article['id']}")).json()["tags"]] == ["dwarrow"]

    async def test_subtype_rename_refreshes_cached_articles(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        article = await create_article(title="Aurora Temple", subtype="shrine", status="published")
        await client.get(f"/articles/{article['id']}")

        await client.patch(
            f"/articles/subtypes/{article['subtype']['id']}",
            json={"name": "sanctuary"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert (await client.get(f"/articles/{article['id']}")).json()["subtype"]["name"] == "sanctuary"

    async def test_image_upload_drops_the_article_payload(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        from app import main as app_module
        from app.core.storage.dependencies import get_image_storage_service

        class Storage:
            async def upload_image(self, entity, row_id, content, content_type):
                return f"https://fake/{entity}/{row_id}.png"

            async def delete_image(self, entity, row_id):
                return None

        app_module.app.dependency_overrides[get_image_storage_service] = lambda: Storage()
        try:
            article = await create_article(title="Gallery", status="published")
            headers = {"Authorization": f"Bearer {gm_token}"}
            await client.get(f"/articles/{article['id']}", headers=headers)

            uploaded = await client.post(
                f"/articles/{article['id']}/images",
                files={"image": ("m.png", b"\x89PNG\r\n\x1a\n\x00", "image/png")},
                headers=headers,
            )

            assert uploaded.status_code == 201
            assert await redis_client.exists(article_cache_key(article["id"])) == 0
            fresh = (await client.get(f"/articles/{article['id']}", headers=headers)).json()
            assert [i["id"] for i in fresh["images"]] == [uploaded.json()["id"]]
        finally:
            app_module.app.dependency_overrides.pop(get_image_storage_service, None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleCacheGaps:
    async def test_image_delete_drops_the_article_payload(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        from app import main as app_module
        from app.core.storage.dependencies import get_image_storage_service

        class Storage:
            async def upload_image(self, entity, row_id, content, content_type):
                return f"https://fake/{entity}/{row_id}.png"

            async def delete_image(self, entity, row_id):
                return None

        app_module.app.dependency_overrides[get_image_storage_service] = lambda: Storage()
        try:
            article = await create_article(title="Gallery", status="published")
            headers = {"Authorization": f"Bearer {gm_token}"}
            uploaded = await client.post(
                f"/articles/{article['id']}/images",
                files={"image": ("m.png", b"\x89PNG\r\n\x1a\n\x00", "image/png")},
                headers=headers,
            )
            assert [i["id"] for i in (await client.get(f"/articles/{article['id']}", headers=headers)).json()["images"]]
            assert await redis_client.exists(article_cache_key(article["id"])) == 1

            deleted = await client.delete(f"/articles/{article['id']}/images/{uploaded.json()['id']}", headers=headers)

            assert deleted.status_code == 204
            assert await redis_client.exists(article_cache_key(article["id"])) == 0
            assert (await client.get(f"/articles/{article['id']}", headers=headers)).json()["images"] == []
        finally:
            app_module.app.dependency_overrides.pop(get_image_storage_service, None)

    async def test_subtype_delete_clears_it_from_cached_articles(
        self, client, create_article, gm_token, founder_token, caching_on, redis_client
    ):
        article = await create_article(title="Aurora Temple", subtype="shrine", status="published")
        await client.get(f"/articles/{article['id']}")
        assert (await client.get(f"/articles/{article['id']}")).json()["subtype"]["name"] == "shrine"

        deleted = await client.delete(
            f"/articles/subtypes/{article['subtype']['id']}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert deleted.status_code == 204
        assert (await client.get(f"/articles/{article['id']}")).json()["subtype"] is None

    async def test_a_gm_read_never_leaks_gm_blocks_into_the_next_anonymous_read(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        article = await create_article(
            title="Secrets", status="published", body_markdown=":::note\nhi\n:::\n:::gm\nBalrogborn\n:::"
        )
        gm_view = await client.get(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"})
        assert "Balrogborn" in gm_view.json()["body_markdown"]
        assert await redis_client.exists(article_cache_key(article["id"])) == 1

        anonymous = await client.get(f"/articles/{article['id']}")

        assert anonymous.status_code == 200
        assert "Balrogborn" not in anonymous.text
        gm_again = await client.get(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"})
        assert "Balrogborn" in gm_again.json()["body_markdown"]

    async def test_visibility_change_hides_the_article_from_anonymous_readers_at_once(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        article = await create_article(title="Prep", status="published")
        assert (await client.get(f"/articles/{article['id']}")).status_code == 200

        await client.patch(
            f"/articles/{article['id']}",
            json={"visibility": "gm_only"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert (await client.get(f"/articles/{article['id']}")).status_code == 404

    async def test_parent_change_refreshes_the_cached_payload(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        first = await create_article(title="First", status="published")
        second = await create_article(title="Second", status="published")
        child = await create_article(title="Child", status="published", parent_id=first["id"])
        assert (await client.get(f"/articles/{child['id']}")).json()["parent_id"] == first["id"]

        await client.patch(
            f"/articles/{child['id']}",
            json={"parent_id": second["id"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert (await client.get(f"/articles/{child['id']}")).json()["parent_id"] == second["id"]

    async def test_a_lost_invalidation_cannot_keep_a_withdrawn_article_public(
        self, client, create_article, caching_on, redis_client, db_session
    ):
        from sqlalchemy import update

        from app.constants import ArticleVisibility
        from app.models import Article

        article = await create_article(title="Withdrawn", status="published")
        assert (await client.get(f"/articles/{article['id']}")).status_code == 200
        assert await redis_client.exists(article_cache_key(article["id"])) == 1

        await db_session.execute(
            update(Article).where(Article.id == article["id"]).values(visibility=ArticleVisibility.GM_ONLY)
        )
        await db_session.commit()

        assert await redis_client.exists(article_cache_key(article["id"])) == 1
        assert (await client.get(f"/articles/{article['id']}")).status_code == 404

    async def test_deleting_an_article_with_many_children_purges_the_whole_namespace(
        self, client, create_article, founder_token, caching_on, redis_client, monkeypatch
    ):
        from app.features.articles.crud import service as articles_service

        monkeypatch.setattr(articles_service, "MAX_POINT_INVALIDATIONS", 1)
        parent = await create_article(title="Parent", status="published")
        first = await create_article(title="Child 1", status="published", parent_id=parent["id"])
        second = await create_article(title="Child 2", status="published", parent_id=parent["id"])
        unrelated = await create_article(title="Unrelated", status="published")
        for article in (parent, first, second, unrelated):
            await client.get(f"/articles/{article['id']}")
        assert await redis_client.exists(article_cache_key(unrelated["id"])) == 1

        await client.delete(f"/articles/{parent['id']}", headers={"Authorization": f"Bearer {founder_token}"})

        for article in (parent, first, second, unrelated):
            assert await redis_client.exists(article_cache_key(article["id"])) == 0
        assert (await client.get(f"/articles/{first['id']}")).json()["parent_id"] is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleListCaches:
    async def test_children_follow_a_title_edit_and_a_new_child(
        self, client, create_article, gm_token, caching_on, redis_client
    ):
        headers = {"Authorization": f"Bearer {gm_token}"}
        parent = await create_article(title="Moria", status="published")
        child = await create_article(title="West Gate", status="published", parent_id=parent["id"])
        url = f"/articles/{parent['id']}/children"
        assert [c["title"] for c in (await client.get(url)).json()] == ["West Gate"]

        await client.patch(f"/articles/{child['id']}", json={"title": "East Gate"}, headers=headers)
        assert [c["title"] for c in (await client.get(url)).json()] == ["East Gate"]

        await create_article(title="Deep Hall", status="published", parent_id=parent["id"])
        assert len((await client.get(url)).json()) == 2

    async def test_subtype_list_follows_create_and_rename(self, client, gm_token, caching_on, redis_client):
        headers = {"Authorization": f"Bearer {gm_token}"}
        assert (await client.get("/articles/subtypes?article_type=location")).json() == []

        created = await client.post(
            "/articles/subtypes", json={"article_type": "location", "name": "shrine"}, headers=headers
        )
        assert [s["name"] for s in (await client.get("/articles/subtypes?article_type=location")).json()] == ["shrine"]

        await client.patch(f"/articles/subtypes/{created.json()['id']}", json={"name": "temple"}, headers=headers)
        assert [s["name"] for s in (await client.get("/articles/subtypes?article_type=location")).json()] == ["temple"]
