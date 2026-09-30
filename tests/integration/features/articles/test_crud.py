"""Tests for the article write endpoints (creation, ltree path maintenance, re-parenting)."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleCrud:
    async def test_player_cannot_create_article(self, client, player_token):
        response = await client.post(
            "/articles",
            json={"title": "Khazad-dum", "article_type": "location"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_article(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "Khazad-dum", "article_type": "location"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "Khazad-dum"
        assert body["slug"] == "khazad-dum"
        assert body["status"] == "draft"
        assert body["parent_id"] is None

    async def test_create_article_rejects_unknown_article_type(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "Mystery", "article_type": "not_a_real_type"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_create_article_rejects_missing_parent(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "Orphan", "article_type": "location", "parent_id": 999999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_create_root_article_sets_path_and_is_its_own_root(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        response = await client.post(
            "/articles",
            json={"title": "Middle-earth", "article_type": "region"},
            headers=headers,
        )
        assert response.status_code == 201
        article_id = response.json()["id"]

        descendants = await client.get(f"/articles/{article_id}/descendants", headers=headers)
        assert descendants.status_code == 200
        assert descendants.json() == []

    async def test_create_child_article_appears_under_parent(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        parent_response = await client.post(
            "/articles",
            json={"title": "Moria Region", "article_type": "region"},
            headers=headers,
        )
        parent_id = parent_response.json()["id"]

        child_response = await client.post(
            "/articles",
            json={"title": "Khazad-dum City", "article_type": "location", "parent_id": parent_id},
            headers=headers,
        )
        assert child_response.status_code == 201
        child_id = child_response.json()["id"]
        assert child_response.json()["parent_id"] == parent_id

        children = await client.get(f"/articles/{parent_id}/children", headers=headers)
        assert children.status_code == 200
        assert [c["id"] for c in children.json()] == [child_id]

        descendants = await client.get(f"/articles/{parent_id}/descendants", headers=headers)
        assert [d["id"] for d in descendants.json()] == [child_id]

        ancestors = await client.get(f"/articles/{child_id}/ancestors", headers=headers)
        assert [a["id"] for a in ancestors.json()] == [parent_id]

    async def test_reparent_article_moves_subtree(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}

        region_a = (
            await client.post("/articles", json={"title": "Region A", "article_type": "region"}, headers=headers)
        ).json()
        region_b = (
            await client.post("/articles", json={"title": "Region B", "article_type": "region"}, headers=headers)
        ).json()
        city = (
            await client.post(
                "/articles",
                json={"title": "City", "article_type": "location", "parent_id": region_a["id"]},
                headers=headers,
            )
        ).json()
        district = (
            await client.post(
                "/articles",
                json={"title": "District", "article_type": "location", "parent_id": city["id"]},
                headers=headers,
            )
        ).json()

        response = await client.patch(
            f"/articles/{city['id']}", json={"parent_id": region_b["id"]}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["parent_id"] == region_b["id"]

        descendants_b = await client.get(f"/articles/{region_b['id']}/descendants", headers=headers)
        assert {d["id"] for d in descendants_b.json()} == {city["id"], district["id"]}

        descendants_a = await client.get(f"/articles/{region_a['id']}/descendants", headers=headers)
        assert descendants_a.json() == []

    async def test_reparent_rejects_cycle(self, client, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}

        parent = (
            await client.post("/articles", json={"title": "Parent", "article_type": "region"}, headers=headers)
        ).json()
        child = (
            await client.post(
                "/articles",
                json={"title": "Child", "article_type": "location", "parent_id": parent["id"]},
                headers=headers,
            )
        ).json()

        response = await client.patch(
            f"/articles/{parent['id']}", json={"parent_id": child["id"]}, headers=headers
        )

        assert response.status_code == 400

    async def test_rename_draft_regenerates_slug(self, client, create_article, gm_token):
        article = await create_article(title="Working Title")

        response = await client.patch(
            f"/articles/{article['id']}", json={"title": "Khazad-dum"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["slug"] == "khazad-dum"

    async def test_rename_draft_keeps_own_slug_without_suffix(self, client, create_article, gm_token):
        article = await create_article(title="Khazad-dum")

        response = await client.patch(
            f"/articles/{article['id']}", json={"title": "KHAZAD-DUM"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.json()["slug"] == "khazad-dum"

    async def test_rename_draft_gets_suffix_when_slug_taken(self, client, create_article, gm_token):
        await create_article(title="Moria")
        article = await create_article(title="Working Title")

        response = await client.patch(
            f"/articles/{article['id']}", json={"title": "Moria"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.json()["slug"] == "moria-2"

    async def test_rename_published_article_keeps_slug(self, client, create_article, gm_token):
        article = await create_article(title="Khazad-dum", status="published")

        response = await client.patch(
            f"/articles/{article['id']}", json={"title": "Moria"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.json()["title"] == "Moria"
        assert response.json()["slug"] == "khazad-dum"
