"""Tag usage aggregation: counts only for what is listed, sort modes, visibility, bounds, delete cache scope."""

import pytest

from app.settings import settings


async def _make_tags(client, gm_token, *names):
    headers = {"Authorization": f"Bearer {gm_token}"}
    return [(await client.post("/tags", json={"name": n}, headers=headers)).json()["id"] for n in names]


@pytest.mark.integration
@pytest.mark.asyncio
class TestUsageListing:
    async def test_name_sort_counts_usage_per_listed_tag_across_catalogs(
        self, client, create_article, create_race, gm_token
    ):
        alpha, beta, gamma = await _make_tags(client, gm_token, "Alpha", "Beta", "Gamma")
        headers = {"Authorization": f"Bearer {gm_token}"}
        await create_article(title="One", tag_ids=[alpha, beta], status="published")
        await create_article(title="Two", tag_ids=[alpha], status="published")
        race = await create_race(name="Elf")
        await client.put(f"/races/{race.id}/tags", json={"tag_ids": [alpha, gamma]}, headers=headers)

        body = (await client.get("/tags", params={"sort": "name"}, headers=headers)).json()

        assert [(t["name"], t["usage_count"]) for t in body["items"]] == [("Alpha", 3), ("Beta", 1), ("Gamma", 1)]
        assert body["total"] == 3

    async def test_name_sort_second_page_has_its_own_counts(self, client, create_article, gm_token):
        alpha, beta, gamma = await _make_tags(client, gm_token, "Alpha", "Beta", "Gamma")
        await create_article(title="One", tag_ids=[gamma], status="published")

        body = (
            await client.get(
                "/tags", params={"sort": "name", "page": 2, "size": 2}, headers={"Authorization": f"Bearer {gm_token}"}
            )
        ).json()

        assert body["total"] == 3
        assert [(t["name"], t["usage_count"]) for t in body["items"]] == [("Gamma", 1)]

    async def test_popular_sort_orders_by_usage_then_name(self, client, create_article, gm_token):
        alpha, beta, gamma = await _make_tags(client, gm_token, "Alpha", "Beta", "Gamma")
        await create_article(title="One", tag_ids=[beta, gamma], status="published")
        await create_article(title="Two", tag_ids=[gamma], status="published")

        body = (
            await client.get("/tags", params={"sort": "popular"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        assert [(t["name"], t["usage_count"]) for t in body["items"]] == [("Gamma", 2), ("Beta", 1), ("Alpha", 0)]

    async def test_popular_sort_paginates_after_ordering(self, client, create_article, gm_token):
        alpha, beta, gamma = await _make_tags(client, gm_token, "Alpha", "Beta", "Gamma")
        await create_article(title="One", tag_ids=[gamma], status="published")

        body = (
            await client.get(
                "/tags",
                params={"sort": "popular", "page": 2, "size": 1},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()

        assert [t["name"] for t in body["items"]] == ["Alpha"]
        assert body["total"] == 3

    async def test_non_gm_total_and_counts_only_cover_visible_records(self, client, create_article, gm_token):
        shown, only_draft, unused = await _make_tags(client, gm_token, "Shown", "OnlyDraft", "Unused")
        await create_article(title="Public", tag_ids=[shown], status="published")
        await create_article(title="Draft", tag_ids=[shown, only_draft])

        for sort in ("name", "popular"):
            body = (await client.get("/tags", params={"sort": sort})).json()

            assert body["total"] == 1
            assert [(t["name"], t["usage_count"]) for t in body["items"]] == [("Shown", 1)]

    async def test_suggest_counts_usage_and_prefers_prefix_then_usage(self, client, create_article, gm_token):
        used, unused, infix = await _make_tags(client, gm_token, "Dwarven", "Dwarf", "Underdwarf")
        await create_article(title="One", tag_ids=[used, infix], status="published")
        await create_article(title="Two", tag_ids=[used], status="published")

        suggested = (await client.get("/tags/suggest", params={"q": "dwar"})).json()

        assert [(t["name"], t["usage_count"]) for t in suggested] == [("Dwarven", 2), ("Underdwarf", 1)]

    async def test_suggest_for_gm_includes_unused_tags(self, client, gm_token):
        await _make_tags(client, gm_token, "Dwarven", "Dwarf")

        suggested = (
            await client.get("/tags/suggest", params={"q": "dwar"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        assert sorted((t["name"], t["usage_count"]) for t in suggested) == [("Dwarf", 0), ("Dwarven", 0)]

    async def test_search_wildcards_are_matched_literally(self, client, gm_token):
        await _make_tags(client, gm_token, "100% Orc", "Plain")

        body = (
            await client.get("/tags", params={"search": "%"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        assert [t["name"] for t in body["items"]] == ["100% Orc"]

    async def test_overlong_search_is_rejected(self, client):
        assert (await client.get("/tags", params={"search": "x" * 101})).status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestTagCache:
    async def test_delete_purges_only_the_tag_namespace(
        self, client, gm_token, founder_token, create_article, redis_client, monkeypatch
    ):
        from app.core.cache.client import cache_set

        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 300)
        [tag] = await _make_tags(client, gm_token, "Dwarven")
        article = await create_article(title="Khazad-dum", status="published")
        await client.get(f"/tags/{tag}")
        await client.get(f"/articles/{article['id']}")
        unrelated = f"{settings.CACHE_PREFIX}:articles:probe:1=x"
        await cache_set(unrelated, "v", 60)

        deleted = await client.delete(f"/tags/{tag}", headers={"Authorization": f"Bearer {founder_token}"})

        assert deleted.status_code == 204
        assert await redis_client.exists(unrelated) == 1
        assert (await client.get(f"/tags/{tag}")).status_code == 404
