"""Quests and sessions: out of the knowledge-base listing/search, in the GM-only campaign-materials endpoints."""

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
