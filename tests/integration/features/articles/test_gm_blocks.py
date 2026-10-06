"""GM-only blocks: nested ``:::`` containers are rejected on write and fail closed on read for legacy rows."""

import pytest
from sqlalchemy import text

NESTED = ":::gm\nBalrogborn sleeps\n:::spoiler\nx\n:::\nmore Balrogborn\n:::\npublic tail"


async def _force_body(db_session, article_id, *, body=None, excerpt=None):
    """Write text straight into the row, the way a legacy (pre-validation) article would hold it."""

    if body is not None:
        await db_session.execute(
            text("UPDATE articles SET body_markdown = :v WHERE id = :id"), {"v": body, "id": article_id}
        )
    if excerpt is not None:
        await db_session.execute(
            text("UPDATE articles SET excerpt = :v WHERE id = :id"), {"v": excerpt, "id": article_id}
        )
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestNestedContainersRejectedOnWrite:
    async def test_create_rejects_nested_container_in_body(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "Fort", "article_type": "location", "body_markdown": NESTED},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_create_rejects_nested_container_in_excerpt(self, client, gm_token):
        response = await client.post(
            "/articles",
            json={"title": "Fort", "article_type": "location", "excerpt": ":::gm x :::note y ::: z :::"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_patch_rejects_nested_container(self, client, create_article, gm_token):
        article = await create_article()

        response = await client.patch(
            f"/articles/{article['id']}",
            json={"body_markdown": NESTED},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_flat_gm_block_next_to_other_containers_is_accepted(self, client, create_article):
        article = await create_article(body_markdown=":::note\nhi\n:::\n:::gm\nsecret\n:::")

        assert article["body_markdown"].startswith(":::note")

    async def test_relation_note_rejects_nested_container(self, client, create_article, gm_token):
        a, b = await create_article(title="A"), await create_article(title="B")

        response = await client.post(
            f"/articles/{a['id']}/relations",
            json={"to_article_id": b["id"], "relation_type": "MENTIONS", "note": NESTED},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestLegacyNestedContainersFailClosed:
    async def test_read_strips_the_whole_block_including_the_tail(self, client, create_article, db_session):
        article = await create_article(title="Fort", status="published")
        await _force_body(db_session, article["id"], body=NESTED)

        anonymous = (await client.get(f"/articles/{article['id']}")).json()

        assert "Balrogborn" not in anonymous["body_markdown"]
        assert anonymous["body_markdown"].endswith("public tail")

    async def test_gm_still_sees_everything(self, client, create_article, db_session, gm_token):
        article = await create_article(title="Fort", status="published")
        await _force_body(db_session, article["id"], body=NESTED)

        gm_view = (
            await client.get(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        assert gm_view["body_markdown"] == NESTED

    async def test_excerpt_in_read_listing_and_search_is_stripped(self, client, create_article, db_session):
        article = await create_article(title="Riverside Fort", status="published")
        await _force_body(db_session, article["id"], excerpt=":::gm Balrogborn :::note x ::: more Balrogborn :::")

        detail = (await client.get(f"/articles/{article['id']}")).json()
        listed = (await client.get("/articles")).json()["items"][0]
        found = (await client.get("/articles/search", params={"q": "Riverside"})).json()["items"][0]

        for payload in (detail, listed, found):
            assert "Balrogborn" not in (payload["excerpt"] or "")
        assert "Balrogborn" not in (found["snippet"] or "")

    async def test_snippet_does_not_show_the_tail_of_a_nested_block(self, client, create_article, db_session):
        article = await create_article(title="Riverside Watchtower", status="published")
        await _force_body(db_session, article["id"], body="Riverside Watchtower guards the ford.\n" + NESTED)

        found = (await client.get("/articles/search", params={"q": "Riverside"})).json()["items"][0]

        assert "Balrogborn" not in (found["snippet"] or "")

    async def test_relation_note_with_nested_block_is_stripped_for_non_gm(
        self, client, create_article, db_session, gm_token
    ):
        a, b = await create_article(title="A", status="published"), await create_article(title="B", status="published")
        created = await client.post(
            f"/articles/{a['id']}/relations",
            json={"to_article_id": b["id"], "relation_type": "MENTIONS", "note": "ok"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        await db_session.execute(
            text("UPDATE article_relations SET note = :v WHERE id = :id"),
            {"v": "see :::gm secret :::note x ::: more secret ::: end", "id": created.json()["id"]},
        )
        await db_session.commit()

        note = (await client.get(f"/articles/{a['id']}/relations")).json()[0]["note"]

        assert "secret" not in note


@pytest.mark.integration
@pytest.mark.asyncio
class TestRelationNoteLength:
    async def test_note_over_300_chars_is_a_422_not_a_500(self, client, create_article, gm_token):
        a, b = await create_article(title="A"), await create_article(title="B")

        response = await client.post(
            f"/articles/{a['id']}/relations",
            json={"to_article_id": b["id"], "relation_type": "MENTIONS", "note": "n" * 301},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_note_of_exactly_300_chars_is_stored(self, client, create_article, gm_token):
        a, b = await create_article(title="A"), await create_article(title="B")

        response = await client.post(
            f"/articles/{a['id']}/relations",
            json={"to_article_id": b["id"], "relation_type": "MENTIONS", "note": "n" * 300},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert len(response.json()["note"]) == 300

    async def test_patch_note_over_300_chars_is_rejected(self, client, create_article, gm_token):
        a, b = await create_article(title="A"), await create_article(title="B")
        headers = {"Authorization": f"Bearer {gm_token}"}
        rel = (
            await client.post(
                f"/articles/{a['id']}/relations",
                json={"to_article_id": b["id"], "relation_type": "MENTIONS"},
                headers=headers,
            )
        ).json()

        response = await client.patch(
            f"/articles/{a['id']}/relations/{rel['id']}", json={"note": "n" * 301}, headers=headers
        )

        assert response.status_code == 422
