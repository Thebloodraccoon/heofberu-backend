"""Tests for the article subtype dictionary (/articles/subtypes) and how articles use it."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleSubtypes:
    @pytest.fixture
    def gm_headers(self, gm_token):
        return {"Authorization": f"Bearer {gm_token}"}

    async def _create(self, client, headers, article_type="location", name="Tavern"):
        payload = {"article_type": article_type, "name": name}
        response = await client.post("/articles/subtypes", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    async def test_gm_creates_subtype(self, client, gm_headers):
        subtype = await self._create(client, gm_headers, name="  Tavern  ")

        assert subtype["article_type"] == "location"
        assert subtype["name"] == "tavern"

    async def test_subtype_names_are_lowercased_on_create_and_rename(self, client, gm_headers):
        subtype = await self._create(client, gm_headers, name="Таверна")

        renamed = await client.patch(
            f"/articles/subtypes/{subtype['id']}", json={"name": "Постоялый ДВОР"}, headers=gm_headers
        )

        assert subtype["name"] == "таверна"
        assert renamed.json()["name"] == "постоялый двор"

    async def test_player_cannot_create_subtype(self, client, player_token):
        response = await client.post(
            "/articles/subtypes",
            json={"article_type": "location", "name": "Tavern"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_unknown_article_type_rejected(self, client, gm_headers):
        payload = {"article_type": "spaceship", "name": "X"}
        response = await client.post("/articles/subtypes", json=payload, headers=gm_headers)

        assert response.status_code == 422

    async def test_duplicate_name_in_same_type_rejected_ignoring_case(self, client, gm_headers):
        await self._create(client, gm_headers, name="Tavern")

        response = await client.post(
            "/articles/subtypes", json={"article_type": "location", "name": "tavern"}, headers=gm_headers
        )

        assert response.status_code == 409

    async def test_same_name_allowed_in_another_type(self, client, gm_headers):
        await self._create(client, gm_headers, article_type="location", name="Capital")

        await self._create(client, gm_headers, article_type="faction", name="Capital")

    async def test_list_filters_by_article_type(self, client, gm_headers):
        await self._create(client, gm_headers, article_type="location", name="Tavern")
        await self._create(client, gm_headers, article_type="faction", name="Guild")

        response = await client.get("/articles/subtypes", params={"article_type": "location"})

        assert response.status_code == 200
        assert [s["name"] for s in response.json()] == ["tavern"]

    async def test_article_embeds_subtype_and_filters_by_it(self, client, create_article):
        tavern = await create_article(title="Prancing Pony", subtype="Tavern", status="published")
        await create_article(title="Bree", subtype="Town", status="published")

        listed = await client.get("/articles", params={"subtype_id": tavern["subtype"]["id"]})

        assert tavern["subtype"]["name"] == "tavern"
        assert [a["title"] for a in listed.json()["items"]] == ["Prancing Pony"]
        assert listed.json()["items"][0]["subtype"] == tavern["subtype"]

    async def test_rename_shows_in_article(self, client, gm_headers, create_article):
        article = await create_article(subtype="Tavern")

        renamed = await client.patch(
            f"/articles/subtypes/{article['subtype']['id']}", json={"name": "Inn"}, headers=gm_headers
        )
        fetched = await client.get(f"/articles/{article['id']}", headers=gm_headers)

        assert renamed.status_code == 200
        assert fetched.json()["subtype"]["name"] == "inn"

    async def test_gm_cannot_delete_subtype(self, client, gm_headers):
        subtype = await self._create(client, gm_headers)

        response = await client.delete(f"/articles/subtypes/{subtype['id']}", headers=gm_headers)

        assert response.status_code == 403

    async def test_founder_delete_clears_it_from_articles(self, client, gm_headers, founder_token, create_article):
        article = await create_article(subtype="Tavern")

        response = await client.delete(
            f"/articles/subtypes/{article['subtype']['id']}", headers={"Authorization": f"Bearer {founder_token}"}
        )
        fetched = await client.get(f"/articles/{article['id']}", headers=gm_headers)

        assert response.status_code == 204
        assert fetched.json()["subtype"] is None

    async def test_article_rejects_subtype_of_another_type(self, client, gm_headers):
        guild = await self._create(client, gm_headers, article_type="faction", name="Guild")

        response = await client.post(
            "/articles",
            json={"title": "Moria", "article_type": "location", "subtype_id": guild["id"]},
            headers=gm_headers,
        )

        assert response.status_code == 400

    async def test_article_rejects_missing_subtype(self, client, gm_headers):
        response = await client.post(
            "/articles", json={"title": "Moria", "article_type": "location", "subtype_id": 999999}, headers=gm_headers
        )

        assert response.status_code == 400

    async def test_changing_type_with_mismatched_subtype_rejected(self, client, gm_headers, create_article):
        article = await create_article(subtype="Tavern")

        response = await client.patch(
            f"/articles/{article['id']}", json={"article_type": "faction"}, headers=gm_headers
        )

        assert response.status_code == 400

    async def test_changing_type_and_clearing_subtype_together(self, client, gm_headers, create_article):
        article = await create_article(subtype="Tavern")

        response = await client.patch(
            f"/articles/{article['id']}", json={"article_type": "faction", "subtype_id": None}, headers=gm_headers
        )

        assert response.status_code == 200
        assert response.json()["article_type"] == "faction"
        assert response.json()["subtype"] is None

    async def test_subtype_refines_only_its_own_type(self, client, create_article):
        tavern = await create_article(title="Prancing Pony", subtype="Tavern", status="published")
        await create_article(title="Bree", subtype="Town", status="published")
        await create_article(title="Barliman", article_type="npc", status="published")
        await create_article(title="Rangers", article_type="faction", status="published")

        response = await client.get(
            "/articles",
            params={"article_type": ["location", "npc"], "subtype_id": tavern["subtype"]["id"]},
        )

        assert sorted(a["title"] for a in response.json()["items"]) == ["Barliman", "Prancing Pony"]

    async def test_several_subtypes_of_one_type(self, client, create_article):
        tavern = await create_article(title="Prancing Pony", subtype="Tavern", status="published")
        town = await create_article(title="Bree", subtype="Town", status="published")
        await create_article(title="Weathertop", subtype="Ruin", status="published")

        response = await client.get(
            "/articles",
            params={"article_type": "location", "subtype_id": [tavern["subtype"]["id"], town["subtype"]["id"]]},
        )

        assert sorted(a["title"] for a in response.json()["items"]) == ["Bree", "Prancing Pony"]

    async def test_subtype_without_its_type_still_filters_search(self, client, create_article):
        tavern = await create_article(title="Old Pony", subtype="Tavern", status="published")
        await create_article(title="Old Bree", subtype="Town", status="published")

        response = await client.get("/articles/search", params={"q": "Old", "subtype_id": tavern["subtype"]["id"]})

        assert [a["title"] for a in response.json()["items"]] == ["Old Pony"]
