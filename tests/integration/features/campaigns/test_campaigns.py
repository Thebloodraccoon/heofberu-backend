"""Game campaigns: ownership, roster, the one-campaign-at-a-time rule and character sheet access."""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCampaignOwnership:
    async def test_only_gms_create_campaigns(self, client, player_token):
        response = await client.post("/campaigns", json={"title": "Mine"}, headers=auth(player_token))

        assert response.status_code == 403

    async def test_title_is_required_without_a_preset(self, client, gm_token):
        response = await client.post("/campaigns", json={}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_founder_cannot_mix_role_with_all_campaigns(self, client, founder_token):
        response = await client.get(
            "/campaigns", params={"all_campaigns": "true", "role": "gm"}, headers=auth(founder_token)
        )

        assert response.status_code == 400

    async def test_other_gm_does_not_see_the_campaign(self, client, make_campaign, other_gm_token):
        campaign = await make_campaign()

        read = await client.get(f"/campaigns/{campaign['id']}", headers=auth(other_gm_token))
        listed = await client.get("/campaigns", headers=auth(other_gm_token))

        assert read.status_code == 404
        assert listed.json()["total"] == 0

    async def test_the_player_sees_their_own_characters_at_each_table(
        self, client, make_campaign, add_character, free_character, player_token, gm_token
    ):
        campaign = await make_campaign()
        await add_character(campaign["id"], free_character.id)

        as_player = await client.get("/campaigns", params={"role": "player"}, headers=auth(player_token))
        detail = await client.get(f"/campaigns/{campaign['id']}", headers=auth(player_token))
        as_gm = await client.get(f"/campaigns/{campaign['id']}", headers=auth(gm_token))

        [row] = as_player.json()["items"]
        assert [(c["character_id"], c["name"], c["status"]) for c in row["my_characters"]] == [
            (free_character.id, "Gurn", "active")
        ]
        assert detail.json()["my_characters"] == row["my_characters"]
        assert as_gm.json()["my_characters"] == []

    async def test_q_searches_campaign_titles(self, client, make_campaign, gm_token):
        await make_campaign(title="Маяк на скале")
        await make_campaign(title="Курган")

        found = await client.get("/campaigns", params={"role": "gm", "q": "маяк"}, headers=auth(gm_token))
        literal = await client.get("/campaigns", params={"role": "gm", "q": "%"}, headers=auth(gm_token))

        assert [row["title"] for row in found.json()["items"]] == ["Маяк на скале"]
        assert literal.json()["items"] == []

    async def test_founder_sees_every_campaign(self, client, make_campaign, founder_token):
        campaign = await make_campaign()

        read = await client.get(f"/campaigns/{campaign['id']}", headers=auth(founder_token))
        listed = await client.get("/campaigns", params={"all_campaigns": True}, headers=auth(founder_token))

        assert read.status_code == 200
        assert read.json()["viewer_role"] == "gm"
        assert [item["id"] for item in listed.json()["items"]] == [campaign["id"]]

    async def test_deleting_the_gm_keeps_the_campaign(
        self, client, gm, founder_token, player_token, make_campaign, add_character, free_character
    ):
        campaign = await make_campaign()
        participation = await add_character(campaign["id"], free_character.id)

        deleted = await client.delete(f"/users/{gm.id}", headers=auth(founder_token))
        player_read = await client.get(f"/campaigns/{campaign['id']}", headers=auth(player_token))
        released = await client.patch(
            f"/campaigns/{campaign['id']}/characters/{participation['id']}",
            json={"status": "retired"},
            headers=auth(founder_token),
        )

        assert deleted.status_code in (200, 204)
        assert player_read.status_code == 200
        assert player_read.json()["owner"] is None
        assert released.json()["status"] == "retired"


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoster:
    async def test_candidates_are_free_characters_by_player_or_name(
        self, client, gm_token, make_campaign, free_character, player
    ):
        campaign = await make_campaign()
        url = f"/campaigns/{campaign['id']}/characters/candidates"

        by_player = await client.get(url, params={"player": player.username}, headers=auth(gm_token))
        by_name = await client.get(url, params={"q": "gur"}, headers=auth(gm_token))

        assert [c["id"] for c in by_player.json()["items"]] == [free_character.id]
        assert by_name.json()["items"][0]["owner"]["username"] == player.username
        assert "backstory" not in by_name.json()["items"][0]

    async def test_player_is_added_without_being_asked_and_sees_the_campaign(
        self, client, make_campaign, add_character, free_character, player_token
    ):
        campaign = await make_campaign(description_markdown="Port town.\n:::gm\nThe mayor is the cultist.\n:::\n")

        added = await add_character(campaign["id"], free_character.id)
        mine = await client.get("/campaigns", headers=auth(player_token))
        read = await client.get(f"/campaigns/{campaign['id']}", headers=auth(player_token))

        assert added["status"] == "active"
        assert [item["viewer_role"] for item in mine.json()["items"]] == ["player"]
        assert read.status_code == 200
        assert "cultist" not in read.json()["description_markdown"]
        assert "Port town." in read.json()["description_markdown"]

    async def test_character_plays_in_one_campaign_at_a_time(
        self, client, make_campaign, add_character, free_character, other_gm_token
    ):
        first = await make_campaign()
        second = await make_campaign(token=other_gm_token, title="Elsewhere")
        await add_character(first["id"], free_character.id)

        again = await client.post(
            f"/campaigns/{second['id']}/characters",
            json={"character_id": free_character.id},
            headers=auth(other_gm_token),
        )
        candidates = await client.get(
            f"/campaigns/{second['id']}/characters/candidates", params={"q": "Gurn"}, headers=auth(other_gm_token)
        )

        assert again.status_code == 409
        assert candidates.json()["items"] == []

    async def test_player_cannot_change_the_roster(
        self, client, make_campaign, add_character, free_character, player_token
    ):
        campaign = await make_campaign()
        participation = await add_character(campaign["id"], free_character.id)

        response = await client.patch(
            f"/campaigns/{campaign['id']}/characters/{participation['id']}",
            json={"status": "removed"},
            headers=auth(player_token),
        )

        assert response.status_code == 403

    async def test_removed_character_is_free_and_the_player_loses_access(
        self, client, gm_token, make_campaign, add_character, free_character, player_token, other_gm_token
    ):
        campaign = await make_campaign()
        participation = await add_character(campaign["id"], free_character.id)

        removed = await client.patch(
            f"/campaigns/{campaign['id']}/characters/{participation['id']}",
            json={"status": "removed"},
            headers=auth(gm_token),
        )
        player_read = await client.get(f"/campaigns/{campaign['id']}", headers=auth(player_token))
        elsewhere = await make_campaign(token=other_gm_token, title="Elsewhere")
        re_added = await client.post(
            f"/campaigns/{elsewhere['id']}/characters",
            json={"character_id": free_character.id},
            headers=auth(other_gm_token),
        )

        assert removed.json()["status"] == "removed"
        assert removed.json()["ended_at"] is not None
        assert player_read.status_code == 404
        assert re_added.status_code == 201

    async def test_active_cannot_be_set_back(self, client, gm_token, make_campaign, add_character, free_character):
        campaign = await make_campaign()
        participation = await add_character(campaign["id"], free_character.id)
        url = f"/campaigns/{campaign['id']}/characters/{participation['id']}"
        await client.patch(url, json={"status": "dead"}, headers=auth(gm_token))

        response = await client.patch(url, json={"status": "active"}, headers=auth(gm_token))

        assert response.status_code == 409

    async def test_finishing_releases_characters_but_players_keep_reading(
        self, client, gm_token, make_campaign, add_character, free_character, player_token
    ):
        campaign = await make_campaign()
        await add_character(campaign["id"], free_character.id)

        await client.patch(f"/campaigns/{campaign['id']}", json={"status": "finished"}, headers=auth(gm_token))
        roster = await client.get(f"/campaigns/{campaign['id']}/characters", headers=auth(gm_token))
        player_read = await client.get(f"/campaigns/{campaign['id']}", headers=auth(player_token))
        add_after = await client.post(
            f"/campaigns/{campaign['id']}/characters",
            json={"character_id": free_character.id},
            headers=auth(gm_token),
        )

        assert [row["status"] for row in roster.json()["items"]] == ["retired"]
        assert player_read.status_code == 200
        assert add_after.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterSheetAccess:
    async def test_gm_role_alone_no_longer_opens_a_sheet(self, client, gm_token, free_character):
        response = await client.get(f"/characters/{free_character.id}", headers=auth(gm_token))

        assert response.status_code == 403

    async def test_campaign_gm_gets_the_sheet_other_gm_does_not(
        self, client, gm_token, make_campaign, add_character, free_character, other_gm_token
    ):
        campaign = await make_campaign()
        await add_character(campaign["id"], free_character.id)

        own_gm = await client.get(f"/characters/{free_character.id}", headers=auth(gm_token))
        other_gm = await client.get(f"/characters/{free_character.id}", headers=auth(other_gm_token))

        assert own_gm.status_code == 200
        assert other_gm.status_code == 403

    async def test_campaign_gm_loses_the_sheet_when_the_character_leaves(
        self, client, gm_token, make_campaign, add_character, free_character
    ):
        campaign = await make_campaign()
        participation = await add_character(campaign["id"], free_character.id)
        await client.patch(
            f"/campaigns/{campaign['id']}/characters/{participation['id']}",
            json={"status": "retired"},
            headers=auth(gm_token),
        )

        response = await client.get(f"/characters/{free_character.id}", headers=auth(gm_token))

        assert response.status_code == 403

    async def test_campaign_gm_cannot_delete_a_players_character(
        self, client, gm_token, make_campaign, add_character, free_character
    ):
        campaign = await make_campaign()
        await add_character(campaign["id"], free_character.id)

        response = await client.delete(f"/characters/{free_character.id}", headers=auth(gm_token))

        assert response.status_code == 403

    async def test_scope_all_lists_only_my_campaigns_characters(
        self, client, gm_token, make_campaign, add_character, free_character, create_character, fighter, player
    ):
        await create_character(owner_id=player.id, class_id=fighter.id, name="Stranger", in_gm_campaign=False)
        campaign = await make_campaign()
        await add_character(campaign["id"], free_character.id)

        response = await client.get("/characters", params={"scope": "all"}, headers=auth(gm_token))

        assert [c["id"] for c in response.json()["items"]] == [free_character.id]
