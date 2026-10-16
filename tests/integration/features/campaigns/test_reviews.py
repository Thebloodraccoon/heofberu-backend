"""Player reviews: of a campaign (public, shown on the preset) and of a session (GM + opt-in table visibility)."""

import pytest
import pytest_asyncio


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def second_player(create_user, login_as, create_character, fighter):
    """Another player with a free character: ``(user, token, character)``."""

    user = await create_user()
    character = await create_character(owner_id=user.id, class_id=fighter.id, name="Ilsa", in_gm_campaign=False)
    return user, await login_as(user), character


@pytest_asyncio.fixture
async def table(make_campaign, add_character, free_character, second_player, make_public_campaign):
    """A campaign made from a published preset, with two players."""

    preset = await make_public_campaign()
    campaign = await make_campaign(public_campaign_id=preset["id"])
    await add_character(campaign["id"], free_character.id)
    await add_character(campaign["id"], second_player[2].id)
    return campaign, preset


@pytest_asyncio.fixture
async def published_session(client, gm_token, table):
    campaign, _ = table
    created = await client.post(f"/campaigns/{campaign['id']}/sessions", json={}, headers=auth(gm_token))
    session_id = created.json()["id"]
    await client.post(f"/campaigns/{campaign['id']}/sessions/{session_id}/publish", headers=auth(gm_token))
    return session_id


@pytest.mark.integration
@pytest.mark.asyncio
class TestCampaignReviews:
    async def test_player_review_shows_on_the_public_campaign(self, client, player_token, table):
        campaign, preset = table

        written = await client.put(
            f"/campaigns/{campaign['id']}/review", json={"body": "Best table ever"}, headers=auth(player_token)
        )
        public = await client.get(f"/public-campaigns/{preset['id']}/reviews")

        assert written.status_code == 200
        assert [review["body"] for review in public.json()["items"]] == ["Best table ever"]

    async def test_second_put_replaces_the_review(self, client, player_token, table):
        campaign, _ = table
        url = f"/campaigns/{campaign['id']}/review"
        await client.put(url, json={"body": "Good"}, headers=auth(player_token))

        second = await client.put(url, json={"body": "Great"}, headers=auth(player_token))
        listed = await client.get(f"/campaigns/{campaign['id']}/reviews", headers=auth(player_token))

        assert second.json()["edited_at"] is not None
        assert [review["body"] for review in listed.json()["items"]] == ["Great"]

    async def test_the_gm_does_not_review_their_own_campaign(self, client, gm_token, table):
        campaign, _ = table

        response = await client.put(f"/campaigns/{campaign['id']}/review", json={"body": "Me"}, headers=auth(gm_token))

        assert response.status_code == 403

    async def test_the_gm_playing_a_character_still_does_not_review(
        self, client, gm, gm_token, table, create_character, fighter, add_character
    ):
        campaign, _ = table
        own = await create_character(owner_id=gm.id, class_id=fighter.id, name="Gm Pc", in_gm_campaign=False)
        await add_character(campaign["id"], own.id)

        response = await client.put(f"/campaigns/{campaign['id']}/review", json={"body": "Me"}, headers=auth(gm_token))

        assert response.status_code == 403

    async def test_a_hidden_review_can_be_deleted_but_not_edited(self, client, player_token, founder_token, table):
        campaign, _ = table
        url = f"/campaigns/{campaign['id']}/review"
        written = await client.put(url, json={"body": "spam"}, headers=auth(player_token))
        await client.post(f"/campaign-reviews/{written.json()['id']}/hide", headers=auth(founder_token))

        edited = await client.put(url, json={"body": "spam, reworded"}, headers=auth(player_token))
        deleted = await client.delete(url, headers=auth(player_token))

        assert edited.status_code == 409
        assert deleted.status_code == 204

    async def test_founder_hides_a_review_everywhere(self, client, player_token, founder_token, table):
        campaign, preset = table
        written = await client.put(
            f"/campaigns/{campaign['id']}/review", json={"body": "spam"}, headers=auth(player_token)
        )

        hidden = await client.post(f"/campaign-reviews/{written.json()['id']}/hide", headers=auth(founder_token))
        public = await client.get(f"/public-campaigns/{preset['id']}/reviews")
        inside = await client.get(f"/campaigns/{campaign['id']}/reviews", headers=auth(player_token))

        assert hidden.status_code == 200
        assert public.json()["items"] == []
        assert inside.json()["items"] == []

    async def test_only_the_founder_moderates(self, client, player_token, gm_token, table):
        campaign, _ = table
        written = await client.put(
            f"/campaigns/{campaign['id']}/review", json={"body": "fine"}, headers=auth(player_token)
        )

        response = await client.post(f"/campaign-reviews/{written.json()['id']}/hide", headers=auth(gm_token))

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestSessionReviews:
    async def test_unpublished_session_cannot_be_reviewed_yet(self, client, gm_token, player_token, table):
        campaign, _ = table
        created = await client.post(f"/campaigns/{campaign['id']}/sessions", json={}, headers=auth(gm_token))

        response = await client.put(
            f"/campaigns/{campaign['id']}/sessions/{created.json()['id']}/review",
            json={"body": "?"},
            headers=auth(player_token),
        )

        # The player sees the session in the schedule; only its chronicle is still closed.
        assert response.status_code == 409

    async def test_session_of_another_campaign_is_404(self, client, gm_token, player_token, table, make_campaign):
        campaign, _ = table
        elsewhere = await make_campaign(title="Elsewhere")
        created = await client.post(f"/campaigns/{elsewhere['id']}/sessions", json={}, headers=auth(gm_token))

        response = await client.put(
            f"/campaigns/{campaign['id']}/sessions/{created.json()['id']}/review",
            json={"body": "?"},
            headers=auth(player_token),
        )

        assert response.status_code == 404

    async def test_gm_reads_all_table_reads_only_opened_ones(
        self, client, gm_token, player_token, second_player, table, published_session
    ):
        campaign, _ = table
        url = f"/campaigns/{campaign['id']}/sessions/{published_session}"
        await client.put(url + "/review", json={"body": "private"}, headers=auth(player_token))
        await client.put(
            url + "/review", json={"body": "for all", "visible_to_table": True}, headers=auth(second_player[1])
        )

        as_gm = await client.get(url + "/reviews", headers=auth(gm_token))
        as_second = await client.get(url + "/reviews", headers=auth(second_player[1]))
        as_first = await client.get(url + "/reviews", headers=auth(player_token))

        assert sorted(review["body"] for review in as_gm.json()["items"]) == ["for all", "private"]
        assert [review["body"] for review in as_second.json()["items"]] == ["for all"]
        assert sorted(review["body"] for review in as_first.json()["items"]) == ["for all", "private"]

    async def test_founder_hides_a_session_review_from_the_gm_and_the_table(
        self, client, gm_token, player_token, second_player, founder_token, table, published_session
    ):
        campaign, _ = table
        url = f"/campaigns/{campaign['id']}/sessions/{published_session}"
        written = await client.put(
            url + "/review", json={"body": "spam", "visible_to_table": True}, headers=auth(player_token)
        )

        hidden = await client.post(f"/session-reviews/{written.json()['id']}/hide", headers=auth(founder_token))
        as_gm = await client.get(url + "/reviews", headers=auth(gm_token))
        as_table = await client.get(url + "/reviews", headers=auth(second_player[1]))
        as_founder = await client.get(url + "/reviews", headers=auth(founder_token))

        assert hidden.status_code == 200
        assert hidden.json()["hidden_at"] is not None
        assert as_gm.json()["items"] == []
        assert as_table.json()["items"] == []
        assert [review["body"] for review in as_founder.json()["items"]] == ["spam"]

    async def test_unhide_shows_the_session_review_again(
        self, client, gm_token, player_token, founder_token, table, published_session
    ):
        campaign, _ = table
        url = f"/campaigns/{campaign['id']}/sessions/{published_session}"
        written = await client.put(url + "/review", json={"body": "fine"}, headers=auth(player_token))
        review_id = written.json()["id"]
        await client.post(f"/session-reviews/{review_id}/hide", headers=auth(founder_token))

        unhidden = await client.post(f"/session-reviews/{review_id}/unhide", headers=auth(founder_token))
        as_gm = await client.get(url + "/reviews", headers=auth(gm_token))

        assert unhidden.json()["hidden_at"] is None
        assert [review["body"] for review in as_gm.json()["items"]] == ["fine"]

    async def test_a_hidden_session_review_can_be_deleted_but_not_edited(
        self, client, player_token, founder_token, table, published_session
    ):
        campaign, _ = table
        url = f"/campaigns/{campaign['id']}/sessions/{published_session}/review"
        written = await client.put(url, json={"body": "spam"}, headers=auth(player_token))
        await client.post(f"/session-reviews/{written.json()['id']}/hide", headers=auth(founder_token))

        edited = await client.put(url, json={"body": "spam, reworded"}, headers=auth(player_token))
        deleted = await client.delete(url, headers=auth(player_token))

        assert edited.status_code == 409
        assert deleted.status_code == 204

    async def test_only_the_founder_moderates_session_reviews(
        self, client, gm_token, player_token, table, published_session
    ):
        campaign, _ = table
        written = await client.put(
            f"/campaigns/{campaign['id']}/sessions/{published_session}/review",
            json={"body": "fine"},
            headers=auth(player_token),
        )

        response = await client.post(f"/session-reviews/{written.json()['id']}/hide", headers=auth(gm_token))

        assert response.status_code == 403

    async def test_hiding_a_missing_session_review_is_404(self, client, founder_token):
        response = await client.post("/session-reviews/999999/hide", headers=auth(founder_token))

        assert response.status_code == 404
