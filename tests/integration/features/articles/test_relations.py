"""Tests for GET/POST/PATCH/DELETE /articles/{id}/relations."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleRelations:
    async def test_player_cannot_create_relation(self, client, create_article, player_token):
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")

        response = await client.post(
            f"/articles/{from_article['id']}/relations",
            json={"to_article_id": to_article["id"], "relation_type": "LOCATED_IN"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_relation(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")

        response = await client.post(
            f"/articles/{from_article['id']}/relations",
            json={"to_article_id": to_article["id"], "relation_type": "LOCATED_IN", "note": "Deep below."},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["relation_type"] == "LOCATED_IN"
        assert body["direction"] == "outgoing"
        assert body["article"]["id"] == to_article["id"]

    async def test_create_relation_rejects_unknown_relation_type(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")

        response = await client.post(
            f"/articles/{from_article['id']}/relations",
            json={"to_article_id": to_article["id"], "relation_type": "NOT_A_REAL_TYPE"},
            headers=headers,
        )

        assert response.status_code == 422

    async def test_create_relation_rejects_self_link(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        article = await create_article(title="Khazad-dum")

        response = await client.post(
            f"/articles/{article['id']}/relations",
            json={"to_article_id": article["id"], "relation_type": "MENTIONS"},
            headers=headers,
        )

        assert response.status_code == 400

    async def test_create_relation_rejects_missing_target(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        article = await create_article(title="Khazad-dum")

        response = await client.post(
            f"/articles/{article['id']}/relations",
            json={"to_article_id": 999999, "relation_type": "MENTIONS"},
            headers=headers,
        )

        assert response.status_code == 400

    async def test_create_duplicate_relation_rejected(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")
        payload = {"to_article_id": to_article["id"], "relation_type": "LOCATED_IN"}

        first = await client.post(f"/articles/{from_article['id']}/relations", json=payload, headers=headers)
        assert first.status_code == 201

        second = await client.post(f"/articles/{from_article['id']}/relations", json=payload, headers=headers)
        assert second.status_code == 409

    async def test_relation_appears_from_both_sides(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")
        await client.post(
            f"/articles/{from_article['id']}/relations",
            json={"to_article_id": to_article["id"], "relation_type": "LOCATED_IN"},
            headers=headers,
        )

        outgoing = await client.get(f"/articles/{from_article['id']}/relations", headers=headers)
        incoming = await client.get(f"/articles/{to_article['id']}/relations", headers=headers)

        assert outgoing.status_code == 200
        assert [r["direction"] for r in outgoing.json()] == ["outgoing"]
        assert incoming.status_code == 200
        assert [r["direction"] for r in incoming.json()] == ["incoming"]

    async def test_gm_only_relation_hidden_from_non_gm(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum", status="published")
        to_article = await create_article(title="Moria", status="published")
        await client.post(
            f"/articles/{from_article['id']}/relations",
            json={"to_article_id": to_article["id"], "relation_type": "MEMBER_OF", "visibility": "gm_only"},
            headers=headers,
        )

        response = await client.get(f"/articles/{from_article['id']}/relations")

        assert response.status_code == 200
        assert response.json() == []

    async def test_gm_block_in_note_stripped_for_non_gm(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum", status="published")
        to_article = await create_article(title="Moria", status="published")
        await client.post(
            f"/articles/{from_article['id']}/relations",
            json={
                "to_article_id": to_article["id"],
                "relation_type": "MEMBER_OF",
                "note": "Sworn member.:::gm Secretly a spy.:::",
            },
            headers=headers,
        )

        anonymous = await client.get(f"/articles/{from_article['id']}/relations")
        gm = await client.get(f"/articles/{from_article['id']}/relations", headers=headers)

        assert anonymous.json()[0]["note"] == "Sworn member."
        assert "spy" in gm.json()[0]["note"]

    async def test_relation_to_hidden_article_hidden_from_non_gm(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum", status="published")
        to_article = await create_article(title="Secret Vault", status="published", visibility="gm_only")
        await client.post(
            f"/articles/{from_article['id']}/relations",
            json={"to_article_id": to_article["id"], "relation_type": "MENTIONS"},
            headers=headers,
        )

        response = await client.get(f"/articles/{from_article['id']}/relations")

        assert response.status_code == 200
        assert response.json() == []

    async def test_gm_can_update_relation(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")
        relation = (
            await client.post(
                f"/articles/{from_article['id']}/relations",
                json={"to_article_id": to_article["id"], "relation_type": "LOCATED_IN"},
                headers=headers,
            )
        ).json()

        response = await client.patch(
            f"/articles/{from_article['id']}/relations/{relation['id']}",
            json={"relation_type": "MENTIONS", "note": "Updated note."},
            headers=headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["relation_type"] == "MENTIONS"
        assert body["note"] == "Updated note."

    async def test_player_cannot_update_relation(self, client, create_article, gm_token, player_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")
        relation = (
            await client.post(
                f"/articles/{from_article['id']}/relations",
                json={"to_article_id": to_article["id"], "relation_type": "LOCATED_IN"},
                headers=headers,
            )
        ).json()

        response = await client.patch(
            f"/articles/{from_article['id']}/relations/{relation['id']}",
            json={"note": "Sneaky edit."},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_delete_relation(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        from_article = await create_article(title="Khazad-dum")
        to_article = await create_article(title="Moria")
        relation = (
            await client.post(
                f"/articles/{from_article['id']}/relations",
                json={"to_article_id": to_article["id"], "relation_type": "LOCATED_IN"},
                headers=headers,
            )
        ).json()

        response = await client.delete(f"/articles/{from_article['id']}/relations/{relation['id']}", headers=headers)

        assert response.status_code == 204

        listed = await client.get(f"/articles/{from_article['id']}/relations", headers=headers)
        assert listed.json() == []

    async def test_delete_missing_relation_returns_404(self, client, create_article, gm_token):
        headers = {"Authorization": f"Bearer {gm_token}"}
        article = await create_article(title="Khazad-dum")

        response = await client.delete(f"/articles/{article['id']}/relations/999999", headers=headers)

        assert response.status_code == 404

    async def test_relations_for_missing_article_returns_404(self, client):
        response = await client.get("/articles/999999/relations")

        assert response.status_code == 404
