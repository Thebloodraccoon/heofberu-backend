"""
Quests and sessions: out of the knowledge-base listing/search, in the GM-only campaign-materials endpoints;
any GM edits them directly (no proposals), only their author or the founder deletes them.
"""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCampaignMaterials:
    async def test_knowledge_base_never_returns_quests_or_sessions(self, client, gm_token, create_article):
        await create_article(title="Lighthouse", article_type="location", status="published")
        await create_article(title="Light the beacon", article_type="quest", status="published")

        listed = await client.get("/articles", headers=auth(gm_token))
        filtered = await client.get("/articles", params={"article_type": "quest"}, headers=auth(gm_token))
        searched = await client.get("/articles/search", params={"q": "light"}, headers=auth(gm_token))

        assert [a["title"] for a in listed.json()["items"]] == ["Lighthouse"]
        assert filtered.json()["items"] == []
        assert [a["title"] for a in searched.json()["items"]] == ["Lighthouse"]

    async def test_campaign_materials_list_and_search_only_them(self, client, gm_token, create_article):
        await create_article(title="Lighthouse", article_type="location", status="published")
        await create_article(title="Light the beacon", article_type="quest", status="published")
        await create_article(title="Session 1: arrival at the light", article_type="session")

        listed = await client.get("/articles/campaign-materials", headers=auth(gm_token))
        only_sessions = await client.get(
            "/articles/campaign-materials", params={"article_type": "session"}, headers=auth(gm_token)
        )
        searched = await client.get(
            "/articles/campaign-materials/search", params={"q": "beacon"}, headers=auth(gm_token)
        )

        titles = sorted(a["title"] for a in listed.json()["items"])
        assert titles == ["Light the beacon", "Session 1: arrival at the light"]
        assert [a["article_type"] for a in only_sessions.json()["items"]] == ["session"]
        assert [a["title"] for a in searched.json()["items"]] == ["Light the beacon"]

    async def test_campaign_materials_are_gm_only(self, client, player_token):
        listed = await client.get("/articles/campaign-materials", headers=auth(player_token))
        guest = await client.get("/articles/campaign-materials")

        assert listed.status_code == 403
        assert guest.status_code == 401

    async def test_a_quest_still_opens_by_id(self, client, create_article):
        quest = await create_article(title="Light the beacon", article_type="quest", status="published")

        response = await client.get(f"/articles/{quest['id']}")

        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestCampaignMaterialRights:
    async def test_any_gm_edits_a_quest_directly(self, client, create_article, other_gm_token):
        quest = await create_article(title="Light the beacon", article_type="quest")

        response = await client.patch(
            f"/articles/{quest['id']}", json={"body_markdown": "Climb the tower."}, headers=auth(other_gm_token)
        )

        assert response.status_code == 200
        assert response.json()["body_markdown"] == "Climb the tower."

    async def test_nobody_proposes_on_a_session(self, client, create_article, other_gm_token):
        session = await create_article(title="Session 1", article_type="session")

        response = await client.post(
            f"/articles/{session['id']}/proposals", json={"body_markdown": "Recap."}, headers=auth(other_gm_token)
        )

        assert response.status_code == 409

    async def test_only_the_author_or_founder_deletes_a_quest(
        self, client, create_article, gm_token, other_gm_token, founder_token
    ):
        mine = await create_article(title="Light the beacon", article_type="quest")
        founders_pick = await create_article(title="Find the keeper", article_type="quest")

        foreign = await client.delete(f"/articles/{mine['id']}", headers=auth(other_gm_token))
        own = await client.delete(f"/articles/{mine['id']}", headers=auth(gm_token))
        by_founder = await client.delete(f"/articles/{founders_pick['id']}", headers=auth(founder_token))

        assert (foreign.status_code, own.status_code, by_founder.status_code) == (403, 204, 204)

    async def test_the_author_still_cannot_delete_a_regular_article(self, client, create_article, gm_token):
        article = await create_article(title="Lighthouse", article_type="location")

        response = await client.delete(f"/articles/{article['id']}", headers=auth(gm_token))

        assert response.status_code == 403
