"""Public campaigns (presets): visibility, author rights, article links, presets for game campaigns, showcase."""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


DESCRIPTION = "A lighthouse on the cliffs.\n:::gm\nThe light lures ships onto the rocks.\n:::\n"


@pytest.mark.integration
@pytest.mark.asyncio
class TestPublicCampaignVisibility:
    async def test_only_gms_create(self, client, player_token):
        response = await client.post("/public-campaigns", json={"title": "Mine"}, headers=auth(player_token))

        assert response.status_code == 403

    async def test_draft_is_hidden_from_guests_and_players(self, client, player_token, gm_token, make_public_campaign):
        draft = await make_public_campaign(publish=False)

        guest = await client.get(f"/public-campaigns/{draft['id']}")
        player = await client.get(f"/public-campaigns/{draft['id']}", headers=auth(player_token))
        gm = await client.get(f"/public-campaigns/{draft['id']}", headers=auth(gm_token))
        catalog = await client.get("/public-campaigns")

        assert (guest.status_code, player.status_code, gm.status_code) == (404, 404, 200)
        assert catalog.json()["items"] == []

    async def test_guests_get_no_gm_blocks_and_no_article_links(
        self, client, gm_token, make_public_campaign, create_article
    ):
        article = await create_article(title="The Keeper", article_type="npc", status="published")
        preset = await make_public_campaign(description_markdown=DESCRIPTION)
        await client.put(
            f"/public-campaigns/{preset['id']}/articles",
            json={"articles": [{"article_id": article["id"], "note": "the villain"}]},
            headers=auth(gm_token),
        )

        guest = (await client.get(f"/public-campaigns/by-slug/{preset['slug']}")).json()
        gm = (await client.get(f"/public-campaigns/{preset['id']}", headers=auth(gm_token))).json()
        links = (await client.get(f"/public-campaigns/{preset['id']}/articles", headers=auth(gm_token))).json()

        assert "lures ships" not in guest["description_markdown"]
        assert "articles" not in guest and "articles" not in gm
        assert "lures ships" in gm["description_markdown"]
        assert [link["title"] for link in links] == ["The Keeper"]

    async def test_only_the_author_or_founder_edits(
        self, client, other_gm_token, founder_token, make_public_campaign
    ):
        preset = await make_public_campaign()
        url = f"/public-campaigns/{preset['id']}"

        other = await client.patch(url, json={"pitch": "hijacked"}, headers=auth(other_gm_token))
        founder = await client.post(url + "/archive", headers=auth(founder_token))

        assert other.status_code == 403
        assert founder.json()["status"] == "archived"

    async def test_slug_is_unique_and_kept_on_rename(self, client, gm_token, make_public_campaign):
        first = await make_public_campaign(title="Маяк")
        second = await make_public_campaign(title="Маяк")

        renamed = await client.patch(
            f"/public-campaigns/{first['id']}", json={"title": "Другой"}, headers=auth(gm_token)
        )

        assert (first["slug"], second["slug"]) == ("mayak", "mayak-2")
        assert renamed.json()["slug"] == "mayak"


@pytest.mark.integration
@pytest.mark.asyncio
class TestCampaignFromPreset:
    async def test_campaign_copies_the_preset_and_counts_on_it(
        self, client, make_public_campaign, make_campaign
    ):
        preset = await make_public_campaign(description_markdown=DESCRIPTION)

        campaign = await make_campaign(title=None, public_campaign_id=preset["id"])
        listed = await client.get("/public-campaigns")

        assert campaign["title"] == preset["title"]
        assert campaign["description_markdown"] == DESCRIPTION
        assert campaign["public_campaign"]["slug"] == preset["slug"]
        assert listed.json()["items"][0]["campaign_count"] == 1

    async def test_counts_are_per_preset_and_zero_without_campaigns(
        self, client, make_public_campaign, make_campaign
    ):
        busy = await make_public_campaign(title="Busy")
        idle = await make_public_campaign(title="Idle")
        for _ in range(2):
            await make_campaign(public_campaign_id=busy["id"])

        listed = (await client.get("/public-campaigns")).json()

        # The grouped count is LEFT JOINed: one row per preset, 0 rather than null, total unaffected.
        assert listed["total"] == 2
        assert {item["title"]: item["campaign_count"] for item in listed["items"]} == {"Busy": 2, "Idle": 0}

    async def test_a_draft_is_its_authors_and_the_founders_only(
        self, client, gm_token, other_gm_token, founder_token, make_public_campaign
    ):
        draft = await make_public_campaign(publish=False)
        catalog = {"status": "draft"}

        other_gm = await client.get(f"/public-campaigns/{draft['id']}", headers=auth(other_gm_token))
        other_gm_catalog = await client.get("/public-campaigns", params=catalog, headers=auth(other_gm_token))
        author_catalog = await client.get("/public-campaigns", params=catalog, headers=auth(gm_token))
        founder = await client.get(f"/public-campaigns/{draft['id']}", headers=auth(founder_token))

        assert other_gm.status_code == 404
        assert other_gm_catalog.json()["items"] == []
        assert [item["id"] for item in author_catalog.json()["items"]] == [draft["id"]]
        assert founder.status_code == 200

    async def test_other_gms_draft_cannot_be_used(self, client, other_gm_token, make_public_campaign):
        draft = await make_public_campaign(publish=False)

        response = await client.post(
            "/campaigns", json={"public_campaign_id": draft["id"]}, headers=auth(other_gm_token)
        )

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestShowcase:
    async def test_characters_appear_only_when_their_owner_shows_them(
        self, client, player_token, make_public_campaign, make_campaign, add_character, free_character
    ):
        preset = await make_public_campaign()
        campaign = await make_campaign(public_campaign_id=preset["id"])
        await add_character(campaign["id"], free_character.id)
        url = f"/public-campaigns/{preset['id']}/characters"

        hidden = await client.get(url)
        await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "concept"},
            headers=auth(player_token),
        )
        shown = await client.get(url)

        assert hidden.json()["items"] == []
        assert [card["name"] for card in shown.json()["items"]] == ["Gurn"]
        assert "title" not in shown.json()["items"][0]

    async def test_removed_characters_leave_the_showcase(
        self, client, gm_token, player_token, make_public_campaign, make_campaign, add_character, free_character
    ):
        preset = await make_public_campaign()
        campaign = await make_campaign(public_campaign_id=preset["id"])
        participation = await add_character(campaign["id"], free_character.id)
        await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "full"},
            headers=auth(player_token),
        )

        await client.patch(
            f"/campaigns/{campaign['id']}/characters/{participation['id']}",
            json={"status": "removed"},
            headers=auth(gm_token),
        )
        response = await client.get(f"/public-campaigns/{preset['id']}/characters")

        assert response.json()["items"] == []
