"""Tests for article editing rights and the version history (revisions, diff, restore)."""

import pytest
import pytest_asyncio

from app.constants import UserRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_gm_token(create_user, login_as):
    """Token of a second GM, who did not write the articles the tests create."""

    return await login_as(await create_user(role=UserRole.GM))


async def _edit(client, article_id, token, **fields):
    return await client.patch(f"/articles/{article_id}", json=fields, headers=_auth(token))


async def _history(client, article_id, token) -> list[dict]:
    response = await client.get(f"/articles/{article_id}/revisions", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["items"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestEditRights:
    async def test_author_edits_own_draft(self, client, create_article, gm_token):
        article = await create_article()

        response = await _edit(client, article["id"], gm_token, title="Moria")

        assert response.status_code == 200

    async def test_other_gm_cannot_edit(self, client, create_article, other_gm_token):
        article = await create_article()

        response = await _edit(client, article["id"], other_gm_token, title="Hijacked")

        assert response.status_code == 403

    async def test_other_gm_cannot_edit_published(self, client, create_article, other_gm_token):
        article = await create_article(status="published")

        response = await _edit(client, article["id"], other_gm_token, body_markdown="vandalism")

        assert response.status_code == 403

    async def test_author_edits_own_published_article_in_place(self, client, create_article, gm_token):
        article = await create_article(status="published")

        response = await _edit(client, article["id"], gm_token, body_markdown="Updated lore")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "published"
        assert body["version"] == 2

    async def test_author_edits_article_in_review(self, client, create_article, gm_token):
        article = await create_article(status="in_review")

        response = await _edit(client, article["id"], gm_token, body_markdown="Fixed a typo")

        assert response.status_code == 200
        assert response.json()["status"] == "in_review"

    async def test_founder_edits_any_article(self, client, create_article, founder_token):
        article = await create_article(status="published")

        response = await _edit(client, article["id"], founder_token, title="Edited by the founder")

        assert response.status_code == 200

    async def test_player_cannot_edit(self, client, create_article, player_token):
        article = await create_article()

        response = await _edit(client, article["id"], player_token, title="Nope")

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestVersioning:
    async def test_new_article_starts_at_version_one(self, client, create_article, gm_token, gm):
        article = await create_article(title="Khazad-dum", body_markdown="First draft")

        assert article["version"] == 1
        history = await _history(client, article["id"], gm_token)
        assert [(r["version"], r["title"], r["editor_id"]) for r in history] == [(1, "Khazad-dum", gm.id)]

    async def test_content_edit_adds_a_version_with_note(self, client, create_article, gm_token):
        article = await create_article(body_markdown="v1")

        response = await _edit(client, article["id"], gm_token, body_markdown="v2", change_note="Rewrote intro")

        assert response.json()["version"] == 2
        history = await _history(client, article["id"], gm_token)
        assert [r["version"] for r in history] == [2, 1]
        assert history[0]["change_note"] == "Rewrote intro"

    async def test_move_alone_is_not_a_new_version(self, client, create_article, gm_token):
        parent = await create_article(title="Eriador")
        article = await create_article(title="Rivendell")

        response = await _edit(client, article["id"], gm_token, parent_id=parent["id"])

        assert response.json()["version"] == 1
        assert len(await _history(client, article["id"], gm_token)) == 1

    async def test_editor_is_recorded_per_version(self, client, create_article, gm_token, founder_token, gm):
        article = await create_article()
        await _edit(client, article["id"], founder_token, body_markdown="founder was here")

        history = await _history(client, article["id"], gm_token)

        assert history[0]["editor_id"] != gm.id
        assert history[1]["editor_id"] == gm.id

    async def test_version_is_hidden_from_non_gm_readers(self, client, create_article, gm_token):
        article = await create_article(status="published")

        public = await client.get(f"/articles/{article['id']}")
        by_slug = await client.get(f"/articles/by-slug/{article['slug']}")
        gm_view = await client.get(f"/articles/{article['id']}", headers=_auth(gm_token))

        assert public.json()["version"] is None
        assert by_slug.json()["version"] is None
        assert gm_view.json()["version"] == 1

    async def test_history_is_gm_only(self, client, create_article, player_token):
        article = await create_article(status="published")

        response = await client.get(f"/articles/{article['id']}/revisions", headers=_auth(player_token))

        assert response.status_code == 403
        assert (await client.get(f"/articles/{article['id']}/revisions")).status_code in (401, 403)

    async def test_history_of_missing_article_is_404(self, client, gm_token):
        response = await client.get("/articles/999999/revisions", headers=_auth(gm_token))

        assert response.status_code == 404

    async def test_get_one_revision_returns_full_snapshot(self, client, create_article, gm_token):
        article = await create_article(body_markdown="old\n\n:::gm\nsecret\n:::")
        await _edit(client, article["id"], gm_token, body_markdown="new")

        response = await client.get(f"/articles/{article['id']}/revisions/1", headers=_auth(gm_token))

        assert response.status_code == 200
        assert response.json()["body_markdown"] == "old\n\n:::gm\nsecret\n:::"
        missing = await client.get(f"/articles/{article['id']}/revisions/9", headers=_auth(gm_token))
        assert missing.status_code == 404

    async def test_diff_defaults_to_previous_version(self, client, create_article, gm_token):
        article = await create_article(title="Moria", body_markdown="line one\nline two")
        await _edit(client, article["id"], gm_token, title="Khazad-dum", body_markdown="line one\nline 2")

        response = await client.get(f"/articles/{article['id']}/revisions/2/diff", headers=_auth(gm_token))

        assert response.status_code == 200
        body = response.json()
        assert (body["version"], body["against"]) == (2, 1)
        assert body["fields"] == {"title": {"old": "Moria", "new": "Khazad-dum"}}
        assert "-line two" in body["body_diff"]
        assert "+line 2" in body["body_diff"]

    async def test_diff_of_first_version_is_all_additions(self, client, create_article, gm_token):
        article = await create_article(body_markdown="hello")

        response = await client.get(f"/articles/{article['id']}/revisions/1/diff", headers=_auth(gm_token))

        body = response.json()
        assert body["against"] == 0
        assert "+hello" in body["body_diff"]

    async def test_restore_makes_old_content_current_as_new_version(self, client, create_article, gm_token):
        article = await create_article(title="Moria", body_markdown="original")
        await _edit(client, article["id"], gm_token, title="Renamed", body_markdown="changed")

        response = await client.post(f"/articles/{article['id']}/revisions/1/restore", headers=_auth(gm_token))

        assert response.status_code == 200
        body = response.json()
        assert (body["title"], body["body_markdown"], body["version"]) == ("Moria", "original", 3)
        history = await _history(client, article["id"], gm_token)
        assert [r["version"] for r in history] == [3, 2, 1]
        assert history[0]["change_note"] == "Restored version 1"

    async def test_restore_keeps_status_and_slug(self, client, create_article, gm_token):
        article = await create_article(status="published", body_markdown="original")
        await _edit(client, article["id"], gm_token, body_markdown="changed")

        body = (await client.post(f"/articles/{article['id']}/revisions/1/restore", headers=_auth(gm_token))).json()

        assert body["status"] == "published"
        assert body["slug"] == article["slug"]

    async def test_other_gm_cannot_restore(self, client, create_article, gm_token, other_gm_token):
        article = await create_article(body_markdown="original")
        await _edit(client, article["id"], gm_token, body_markdown="changed")

        response = await client.post(f"/articles/{article['id']}/revisions/1/restore", headers=_auth(other_gm_token))

        assert response.status_code == 403

    async def test_restore_unknown_version_is_404(self, client, create_article, gm_token):
        article = await create_article()

        response = await client.post(f"/articles/{article['id']}/revisions/7/restore", headers=_auth(gm_token))

        assert response.status_code == 404

    async def test_deleting_the_article_deletes_its_history(self, client, create_article, gm_token, founder_token):
        article = await create_article()
        await _edit(client, article["id"], gm_token, body_markdown="v2")

        assert (await client.delete(f"/articles/{article['id']}", headers=_auth(founder_token))).status_code == 204

        assert (await client.get(f"/articles/{article['id']}/revisions", headers=_auth(gm_token))).status_code == 404
