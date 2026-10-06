"""Tests for the shared tags dictionary CRUD (/tags)."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestTagCrud:
    async def test_player_cannot_create_tag(self, client, player_token):
        response = await client.post(
            "/tags", json={"name": "Dwarven"}, headers={"Authorization": f"Bearer {player_token}"}
        )

        assert response.status_code == 403

    async def test_gm_can_create_tag(self, client, gm_token):
        response = await client.post("/tags", json={"name": "Dwarven"}, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "dwarven"

    async def test_create_tag_rejects_case_insensitive_duplicate(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        await client.post("/tags", json={"name": "Dwarven"}, headers=headers)

        response = await client.post("/tags", json={"name": "dwarven"}, headers=headers)

        assert response.status_code == 409

    async def test_create_tag_normalizes_whitespace(self, client, gm_token):
        response = await client.post(
            "/tags", json={"name": "  Dwarven   Kingdom  "}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 201
        assert response.json()["name"] == "dwarven kingdom"

    async def test_tag_names_are_lowercased_on_create_and_rename(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        created = (await client.post("/tags", json={"name": "Северные Дварфы"}, headers=headers)).json()

        renamed = await client.patch(f"/tags/{created['id']}", json={"name": "Горные ДВАРФЫ"}, headers=headers)

        assert created["name"] == "северные дварфы"
        assert renamed.json()["name"] == "горные дварфы"

    async def test_create_tag_rejects_blank_name(self, client, gm_token):
        response = await client.post("/tags", json={"name": "   "}, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 422

    async def test_get_tag_by_id(self, client, gm_token):
        created = (
            await client.post("/tags", json={"name": "Dwarven"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        response = await client.get(f"/tags/{created['id']}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200
        assert response.json()["name"] == "dwarven"

    async def test_get_missing_tag_returns_404(self, client):
        response = await client.get("/tags/999999")

        assert response.status_code == 404

    async def test_gm_can_rename_tag(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        created = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()

        response = await client.patch(f"/tags/{created['id']}", json={"name": "Dwarrow"}, headers=headers)

        assert response.status_code == 200
        assert response.json()["name"] == "dwarrow"

    async def test_player_cannot_rename_tag(self, client, gm_token, player_token):
        created = (
            await client.post("/tags", json={"name": "Dwarven"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        response = await client.patch(
            f"/tags/{created['id']}",
            json={"name": "Dwarrow"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_rename_tag_rejects_conflicting_name(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        await client.post("/tags", json={"name": "Dwarven"}, headers=headers)
        second = (await client.post("/tags", json={"name": "Elven"}, headers=headers)).json()

        response = await client.patch(f"/tags/{second['id']}", json={"name": "Dwarven"}, headers=headers)

        assert response.status_code == 409

    async def test_founder_can_delete_unused_tag(self, client, gm_token, founder_token):
        created = (
            await client.post("/tags", json={"name": "Dwarven"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        response = await client.delete(f"/tags/{created['id']}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204

        fetched = await client.get(f"/tags/{created['id']}")
        assert fetched.status_code == 404

    async def test_gm_cannot_delete_tag(self, client, gm_token):
        created = (
            await client.post("/tags", json={"name": "Dwarven"}, headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        response = await client.delete(f"/tags/{created['id']}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403

    async def test_delete_tag_still_in_use_is_rejected(self, client, gm_token, founder_token, create_article):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        await create_article(title="Khazad-dum", tag_ids=[tag["id"]])

        response = await client.delete(f"/tags/{tag['id']}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409

    async def test_list_tags_paginated(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        for name in ("Alpha", "Beta", "Gamma"):
            await client.post("/tags", json={"name": name}, headers=headers)

        response = await client.get("/tags", params={"page": 1, "size": 2, "sort": "name"}, headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert [t["name"] for t in body["items"]] == ["alpha", "beta"]

    async def test_list_tags_filters_by_search(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        await client.post("/tags", json={"name": "Dwarven"}, headers=headers)
        await client.post("/tags", json={"name": "Elven"}, headers=headers)

        response = await client.get("/tags", params={"search": "warv"}, headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "dwarven"

    async def test_list_tags_reports_usage_count(self, client, gm_token, create_article):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        await create_article(title="Khazad-dum", tag_ids=[tag["id"]])

        response = await client.get("/tags", params={"search": "Dwarven"}, headers=headers)

        assert response.status_code == 200
        assert response.json()["items"][0]["usage_count"] == 1

    async def test_suggest_prefers_prefix_match(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        await client.post("/tags", json={"name": "Underground River"}, headers=headers)
        await client.post("/tags", json={"name": "Dwarven"}, headers=headers)

        response = await client.get("/tags/suggest", params={"q": "Dwar"}, headers=headers)

        assert response.status_code == 200
        names = [t["name"] for t in response.json()]
        assert names[0] == "dwarven"

    async def test_suggest_respects_limit(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        for i in range(3):
            await client.post("/tags", json={"name": f"Dwarven {i}"}, headers=headers)

        response = await client.get("/tags/suggest", params={"q": "Dwarven", "limit": 2}, headers=headers)

        assert response.status_code == 200
        assert len(response.json()) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestTagVisibility:
    async def test_tag_only_on_hidden_article_invisible_to_anonymous(self, client, gm_token, create_article):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Traitor"}, headers=headers)).json()
        await create_article(title="Secret Plot", tag_ids=[tag["id"]])

        listed = await client.get("/tags", params={"search": "Traitor"})
        suggested = await client.get("/tags/suggest", params={"q": "Trai"})
        fetched = await client.get(f"/tags/{tag['id']}")

        assert listed.json()["total"] == 0
        assert suggested.json() == []
        assert fetched.status_code == 404

    async def test_tag_on_hidden_article_still_visible_to_gm(self, client, gm_token, create_article):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Traitor"}, headers=headers)).json()
        await create_article(title="Secret Plot", tag_ids=[tag["id"]])

        listed = await client.get("/tags", params={"search": "Traitor"}, headers=headers)
        fetched = await client.get(f"/tags/{tag['id']}", headers=headers)

        assert listed.json()["items"][0]["usage_count"] == 1
        assert fetched.status_code == 200

    async def test_anonymous_usage_count_ignores_hidden_articles(self, client, gm_token, create_article):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Dwarven"}, headers=headers)).json()
        await create_article(title="Khazad-dum", tag_ids=[tag["id"]], status="published")
        await create_article(title="Hidden Hold", tag_ids=[tag["id"]])
        await create_article(title="GM Hold", tag_ids=[tag["id"]], status="published", visibility="gm_only")

        listed = await client.get("/tags", params={"search": "Dwarven"})
        fetched = await client.get(f"/tags/{tag['id']}")

        assert listed.json()["items"][0]["usage_count"] == 1
        assert fetched.status_code == 200
