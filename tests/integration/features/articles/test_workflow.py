"""Tests for the article review workflow: submit / publish / reject / archive / restore."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleWorkflow:
    async def test_new_article_is_draft_and_patch_cannot_change_status(self, client, create_article, gm_token):
        article = await create_article()
        assert article["status"] == "draft"

        response = await client.patch(
            f"/articles/{article['id']}", json={"status": "published"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "draft"

    async def test_gm_can_submit_draft(self, client, create_article, gm_token):
        article = await create_article()

        response = await client.post(
            f"/articles/{article['id']}/submit", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "in_review"

    async def test_player_cannot_submit(self, client, create_article, player_token):
        article = await create_article()

        response = await client.post(
            f"/articles/{article['id']}/submit", headers={"Authorization": f"Bearer {player_token}"}
        )

        assert response.status_code == 403

    async def test_gm_cannot_publish(self, client, create_article, gm_token):
        article = await create_article(status="in_review")

        response = await client.post(
            f"/articles/{article['id']}/publish", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 403

    async def test_founder_publishes_article_under_review(self, client, create_article, founder_token):
        article = await create_article(status="in_review")

        response = await client.post(
            f"/articles/{article['id']}/publish", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "published"
        assert body["published_at"] is not None
        assert (await client.get(f"/articles/{article['id']}")).status_code == 200

    async def test_publish_draft_directly_is_409(self, client, create_article, founder_token):
        article = await create_article()

        response = await client.post(
            f"/articles/{article['id']}/publish", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 409

    async def test_submit_twice_is_409(self, client, create_article, gm_token):
        article = await create_article(status="in_review")

        response = await client.post(
            f"/articles/{article['id']}/submit", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 409

    async def test_founder_rejects_back_to_draft(self, client, create_article, founder_token):
        article = await create_article(status="in_review")

        response = await client.post(
            f"/articles/{article['id']}/reject", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "draft"

    async def test_archive_hides_published_article_from_anonymous(self, client, create_article, founder_token):
        article = await create_article(status="published")

        response = await client.post(
            f"/articles/{article['id']}/archive", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "archived"
        assert (await client.get(f"/articles/{article['id']}")).status_code == 404

    async def test_gm_cannot_archive(self, client, create_article, gm_token):
        article = await create_article(status="published")

        response = await client.post(
            f"/articles/{article['id']}/archive", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 403

    async def test_restore_returns_archived_to_draft(self, client, create_article, founder_token):
        article = await create_article(status="archived")

        response = await client.post(
            f"/articles/{article['id']}/restore", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "draft"

    async def test_restore_non_archived_is_409(self, client, create_article, founder_token):
        article = await create_article()

        response = await client.post(
            f"/articles/{article['id']}/restore", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 409

    async def test_published_at_survives_edit_and_republish(self, client, create_article, gm_token, founder_token):
        gm = {"Authorization": f"Bearer {gm_token}"}
        founder = {"Authorization": f"Bearer {founder_token}"}
        article = await create_article(status="published")
        published_at = article["published_at"]

        edited = await client.patch(f"/articles/{article['id']}", json={"title": "Lorebook Revised"}, headers=gm)
        assert edited.json()["status"] == "published"
        assert edited.json()["published_at"] == published_at

        for action, headers in [("archive", founder), ("restore", founder), ("submit", gm), ("publish", founder)]:
            moved = await client.post(f"/articles/{article['id']}/{action}", headers=headers)
            assert moved.status_code == 200, moved.text

        assert moved.json()["published_at"] == published_at

    async def test_transition_on_missing_article_is_404(self, client, gm_token):
        response = await client.post("/articles/999999/submit", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 404
