"""Tests for GET /articles/search (full-text + trigram ranking, snippets, GM-only stripping)."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleSearch:
    async def test_search_matches_full_word_in_title(self, client, create_article):
        await create_article(title="Aurora the Sun God", status="published")

        response = await client.get("/articles/search", params={"q": "Aurora"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Aurora the Sun God"

    async def test_search_matches_short_prefix_via_trigram(self, client, create_article):
        await create_article(title="Aurora the Sun God", status="published")

        response = await client.get("/articles/search", params={"q": "Aur"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Aurora the Sun God"

    async def test_search_does_not_match_unrelated_short_query(self, client, create_article):
        await create_article(title="Aurora the Sun God", status="published")

        response = await client.get("/articles/search", params={"q": "Zeb"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_snippet_highlights_match_found_in_excerpt(self, client, create_article):
        await create_article(
            title="Ordinary Location",
            excerpt="A hidden vault called Wyrmspire lies beneath.",
            body_markdown="Nothing relevant here, just filler lore text about taverns and roads.",
            status="published",
        )

        response = await client.get("/articles/search", params={"q": "Wyrmspire"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert "<mark>" in body["items"][0]["snippet"]

    async def test_snippet_highlights_match_found_in_title(self, client, create_article):
        await create_article(
            title="Wyrmspire Vault",
            body_markdown="Filler lore text unrelated to the query at all.",
            status="published",
        )

        response = await client.get("/articles/search", params={"q": "Wyrmspire"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert "<mark>" in body["items"][0]["snippet"]

    async def test_draft_article_excluded_from_search(self, client, create_article):
        await create_article(title="Unpublished Draft Aurora")

        response = await client.get("/articles/search", params={"q": "Aurora"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_gm_only_article_excluded_from_anonymous_search(self, client, create_article):
        await create_article(title="Secret Aurora Prep Notes", status="published", visibility="gm_only")

        response = await client.get("/articles/search", params={"q": "Aurora"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_gm_only_article_visible_to_gm_search(self, client, create_article, gm_token):
        await create_article(title="Secret Aurora Prep Notes", status="published", visibility="gm_only")

        response = await client.get(
            "/articles/search",
            params={"q": "Aurora"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_gm_block_content_not_searchable_by_non_gm(self, client, create_article):
        await create_article(
            title="Public Fortress",
            body_markdown="A quiet fortress on the border.\n\n:::gm\nBalrogborn stirs beneath it.\n:::",
            status="published",
        )

        response = await client.get("/articles/search", params={"q": "Balrogborn"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_gm_block_content_searchable_by_gm(self, client, create_article, gm_token):
        await create_article(
            title="Public Fortress",
            body_markdown="A quiet fortress on the border.\n\n:::gm\nBalrogborn stirs beneath it.\n:::",
            status="published",
        )

        response = await client.get(
            "/articles/search",
            params={"q": "Balrogborn"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_gm_block_content_not_leaked_in_non_gm_snippet(self, client, create_article):
        await create_article(
            title="Riverside Watchtower",
            body_markdown="Riverside Watchtower guards the ford.\n\n:::gm\nBalrogborn stirs beneath it.\n:::",
            status="published",
        )

        response = await client.get("/articles/search", params={"q": "Riverside"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        snippet = body["items"][0]["snippet"] or ""
        assert "Balrogborn" not in snippet

    async def test_uppercase_gm_block_content_not_searchable_by_non_gm(self, client, create_article):
        await create_article(
            title="Public Fortress",
            body_markdown="A quiet fortress on the border.\n\n:::GM\nBalrogborn stirs beneath it.\n:::",
            status="published",
        )

        response = await client.get("/articles/search", params={"q": "Balrogborn"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_mixed_case_gm_block_content_not_leaked_in_non_gm_snippet(self, client, create_article):
        await create_article(
            title="Riverside Watchtower",
            body_markdown="Riverside Watchtower guards the ford.\n\n:::Gm\nBalrogborn stirs beneath it.\n:::",
            status="published",
        )

        response = await client.get("/articles/search", params={"q": "Riverside"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert "Balrogborn" not in (body["items"][0]["snippet"] or "")

    async def test_gm_block_in_excerpt_not_searchable_or_shown_to_non_gm(self, client, create_article):
        await create_article(
            title="Public Fortress", excerpt="A border keep.:::gm Balrogborn sleeps here.:::", status="published"
        )

        secret = await client.get("/articles/search", params={"q": "Balrogborn"})
        public = await client.get("/articles/search", params={"q": "Fortress"})

        assert secret.json()["total"] == 0
        hit = public.json()["items"][0]
        assert "Balrogborn" not in (hit["excerpt"] or "")
        assert "Balrogborn" not in (hit["snippet"] or "")

    async def test_search_filters_by_article_type(self, client, create_article):
        await create_article(title="Aurora the Sun God", article_type="deity", status="published")
        await create_article(title="Aurora's Blade", article_type="artifact", status="published")

        response = await client.get("/articles/search", params={"q": "Aurora", "article_type": "deity"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["article_type"] == "deity"

    async def test_search_filters_by_subtype(self, client, create_article):
        temple = await create_article(title="Aurora Temple", subtype="shrine", status="published")
        await create_article(title="Aurora Keep", subtype="fortress", status="published")

        response = await client.get("/articles/search", params={"q": "Aurora", "subtype_id": temple["subtype"]["id"]})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Aurora Temple"
        assert body["items"][0]["subtype"] == temple["subtype"]

    async def test_search_rejects_query_shorter_than_two_chars(self, client):
        response = await client.get("/articles/search", params={"q": "a"})

        assert response.status_code == 422

    async def test_search_paginates_results(self, client, create_article):
        for i in range(3):
            await create_article(title=f"Aurora Entry {i}", status="published")

        response = await client.get("/articles/search", params={"q": "Aurora", "page": 1, "size": 2})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
