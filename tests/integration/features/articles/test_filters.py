"""Listing/search filters (tag_match=all, subtype), query bounds, title normalization and relation listing caps."""

import pytest
from sqlalchemy import delete

from app.models.user_model import User


async def _tag(client, gm_token, name):
    response = await client.post("/tags", json={"name": name}, headers={"Authorization": f"Bearer {gm_token}"})
    return response.json()["id"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestTagMatch:
    async def test_tag_match_any_returns_articles_with_at_least_one_tag(self, client, create_article, gm_token):
        red, blue = await _tag(client, gm_token, "Red"), await _tag(client, gm_token, "Blue")
        await create_article(title="Both", tag_ids=[red, blue], status="published")
        await create_article(title="Only Red", tag_ids=[red], status="published")
        await create_article(title="Neither", status="published")

        response = await client.get("/articles", params={"tag_id": [red, blue], "tag_match": "any"})

        assert {i["title"] for i in response.json()["items"]} == {"Both", "Only Red"}

    async def test_tag_match_all_requires_every_tag(self, client, create_article, gm_token):
        red, blue = await _tag(client, gm_token, "Red"), await _tag(client, gm_token, "Blue")
        await create_article(title="Both", tag_ids=[red, blue], status="published")
        await create_article(title="Only Red", tag_ids=[red], status="published")

        response = await client.get("/articles", params={"tag_id": [red, blue], "tag_match": "all"})

        body = response.json()
        assert [i["title"] for i in body["items"]] == ["Both"]
        assert body["total"] == 1

    async def test_tag_match_all_with_a_repeated_id_is_not_stricter(self, client, create_article, gm_token):
        red = await _tag(client, gm_token, "Red")
        await create_article(title="Red One", tag_ids=[red], status="published")

        response = await client.get("/articles", params={"tag_id": [red, red], "tag_match": "all"})

        assert response.json()["total"] == 1

    async def test_tag_match_all_applies_to_search_too(self, client, create_article, gm_token):
        red, blue = await _tag(client, gm_token, "Red"), await _tag(client, gm_token, "Blue")
        await create_article(title="Aurora Both", tag_ids=[red, blue], status="published")
        await create_article(title="Aurora Red", tag_ids=[red], status="published")

        response = await client.get(
            "/articles/search", params={"q": "Aurora", "tag_id": [red, blue], "tag_match": "all"}
        )

        assert [i["title"] for i in response.json()["items"]] == ["Aurora Both"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestListFilters:
    async def test_list_filters_by_subtype(self, client, create_article):
        shrine = await create_article(title="Shrine", subtype="shrine", status="published")
        await create_article(title="Keep", subtype="fortress", status="published")

        response = await client.get("/articles", params={"subtype_id": shrine["subtype"]["id"]})

        assert [i["title"] for i in response.json()["items"]] == ["Shrine"]

    async def test_more_than_the_allowed_number_of_filter_values_is_rejected(self, client):
        too_many = list(range(1, 52))

        assert (await client.get("/articles", params={"tag_id": too_many})).status_code == 422
        assert (await client.get("/articles", params={"subtype_id": too_many})).status_code == 422
        assert (await client.get("/articles", params={"article_type": ["lore"] * 51})).status_code == 422
        assert (await client.get("/articles/search", params={"q": "ab", "tag_id": too_many})).status_code == 422

    async def test_overlong_article_type_value_is_rejected(self, client):
        assert (await client.get("/articles", params={"article_type": "x" * 51})).status_code == 422

    async def test_fifty_filter_values_are_still_allowed(self, client):
        assert (await client.get("/articles", params={"tag_id": list(range(1, 51))})).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthorFilter:
    async def _setup(self, client, create_article, founder_token):
        """The GM writes a public, a GM-only and a draft article; the founder writes one more."""

        await create_article(title="Public Lore", status="published")
        await create_article(title="Secret Lore", status="published", visibility="gm_only")
        await create_article(title="Draft Lore")
        response = await client.post(
            "/articles",
            json={"title": "Founder Lore", "article_type": "lore"},
            headers={"Authorization": f"Bearer {founder_token}"},
        )
        assert response.status_code == 201, response.text

    async def test_gm_sees_every_article_of_the_author(self, client, create_article, gm_token, founder_token, gm):
        await self._setup(client, create_article, founder_token)

        response = await client.get(
            "/articles", params={"author_id": gm.id}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert {i["title"] for i in response.json()["items"]} == {"Public Lore", "Secret Lore", "Draft Lore"}
        assert {i["author"]["id"] for i in response.json()["items"]} == {gm.id}

    async def test_non_gm_sees_only_the_authors_published_public_articles(
        self, client, create_article, founder_token, player_token, gm
    ):
        await self._setup(client, create_article, founder_token)

        anonymous = await client.get("/articles", params={"author_id": gm.id})
        player = await client.get(
            "/articles", params={"author_id": gm.id}, headers={"Authorization": f"Bearer {player_token}"}
        )

        for response in (anonymous, player):
            body = response.json()
            assert [i["title"] for i in body["items"]] == ["Public Lore"]
            assert body["total"] == 1

    async def test_search_filters_by_author(self, client, create_article, founder_token, gm, founder):
        await self._setup(client, create_article, founder_token)

        mine = await client.get("/articles/search", params={"q": "lore", "author_id": gm.id})
        founders = await client.get("/articles/search", params={"q": "lore", "author_id": founder.id})

        assert [(i["title"], i["author"]["id"]) for i in mine.json()["items"]] == [("Public Lore", gm.id)]
        assert founders.json()["items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthorInResponses:
    async def test_anonymous_reader_sees_author_everywhere(self, client, create_article, gm):
        article = await create_article(title="Public Lore", status="published")
        expected = {"id": gm.id, "username": gm.username}

        detail = (await client.get(f"/articles/{article['id']}")).json()
        listed = (await client.get("/articles")).json()["items"]
        found = (await client.get("/articles/search", params={"q": "lore"})).json()["items"]

        assert detail["author"] == expected
        assert [i["author"] for i in listed] == [expected]
        assert [i["author"] for i in found] == [expected]

    async def test_author_is_null_once_the_user_is_deleted(self, client, create_article, gm, db_session):
        await create_article(title="Orphan", status="published")

        await db_session.execute(delete(User).where(User.id == gm.id))
        await db_session.commit()

        item = (await client.get("/articles")).json()["items"][0]
        assert item["author"] is None
        assert "author_id" not in item


@pytest.mark.integration
@pytest.mark.asyncio
class TestTitleNormalization:
    async def test_blank_title_is_rejected(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "   ", "article_type": "location"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_title_is_trimmed_and_collapsed(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "  Khazad    dum ", "article_type": "location"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.json()["title"] == "Khazad dum"

    async def test_patch_blank_title_is_rejected(self, client, create_article, gm_token):
        article = await create_article()

        response = await client.patch(
            f"/articles/{article['id']}", json={"title": " "}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422

    async def test_oversized_body_is_rejected(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "Big", "article_type": "location", "body_markdown": "a" * 200_001},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestRelationListing:
    async def test_non_gm_listing_filters_in_sql_and_still_returns_visible_relations(
        self, client, create_article, gm_token
    ):
        headers = {"Authorization": f"Bearer {gm_token}"}
        hub = await create_article(title="Hub", status="published")
        visible = await create_article(title="Visible", status="published")
        draft = await create_article(title="Draft")
        for target, visibility in ((visible, "public"), (draft, "public"), (visible, "gm_only")):
            await client.post(
                f"/articles/{hub['id']}/relations",
                json={
                    "to_article_id": target["id"],
                    "relation_type": "MENTIONS" if visibility == "public" else "ALLY_OF",
                    "visibility": visibility,
                },
                headers=headers,
            )

        anonymous = await client.get(f"/articles/{hub['id']}/relations")
        gm = await client.get(f"/articles/{hub['id']}/relations", headers=headers)

        assert [r["article"]["title"] for r in anonymous.json()] == ["Visible"]
        assert len(gm.json()) == 3

    async def test_incoming_relation_from_a_hidden_article_is_hidden_from_non_gm(
        self, client, create_article, gm_token
    ):
        headers = {"Authorization": f"Bearer {gm_token}"}
        public = await create_article(title="Public", status="published")
        secret = await create_article(title="Secret Draft")
        await client.post(
            f"/articles/{secret['id']}/relations",
            json={"to_article_id": public["id"], "relation_type": "MENTIONS"},
            headers=headers,
        )

        assert (await client.get(f"/articles/{public['id']}/relations")).json() == []

    async def test_relation_list_is_capped(self, client, create_article, gm_token, monkeypatch):
        monkeypatch.setattr("app.features.articles.relations.repository.RELATIONS_LIMIT", 2)
        headers = {"Authorization": f"Bearer {gm_token}"}
        hub = await create_article(title="Hub", status="published")
        for i in range(3):
            other = await create_article(title=f"Other {i}", status="published")
            await client.post(
                f"/articles/{hub['id']}/relations",
                json={"to_article_id": other["id"], "relation_type": "MENTIONS"},
                headers=headers,
            )

        assert len((await client.get(f"/articles/{hub['id']}/relations")).json()) == 2
