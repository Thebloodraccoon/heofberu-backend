"""
Campaign sessions (schedule, attendance, archive, chronicle with ``:::gm`` blocks and its publication) and the
GM's private notes.
"""

import pytest
import pytest_asyncio


def auth(token):
    return {"Authorization": f"Bearer {token}"}


CHRONICLE = "The party reached the lighthouse.\n:::gm\nThe keeper is already dead.\n:::\nThey camped outside."


@pytest_asyncio.fixture
async def table(make_campaign, add_character, free_character):
    """A campaign with the default player's character in it."""

    campaign = await make_campaign()
    await add_character(campaign["id"], free_character.id)
    return campaign


@pytest.mark.integration
@pytest.mark.asyncio
class TestSessions:
    async def test_players_see_the_session_but_not_the_unpublished_chronicle(
        self, client, gm_token, player_token, table
    ):
        created = await client.post(
            f"/campaigns/{table['id']}/sessions",
            json={"title": "Arrival", "scheduled_at": "2099-01-10T18:00:00Z", "chronicle_markdown": CHRONICLE},
            headers=auth(gm_token),
        )
        session_id = created.json()["id"]

        player_list = await client.get(f"/campaigns/{table['id']}/sessions", headers=auth(player_token))
        player_read = await client.get(f"/campaigns/{table['id']}/sessions/{session_id}", headers=auth(player_token))

        assert created.status_code == 201
        assert created.json()["number"] == 1
        assert [(row["id"], row["title"]) for row in player_list.json()["items"]] == [(session_id, "Arrival")]
        assert player_read.status_code == 200
        assert player_read.json()["scheduled_at"] is not None
        assert player_read.json()["chronicle_markdown"] is None
        assert created.json()["chronicle_markdown"] == CHRONICLE

    async def test_sessions_are_paginated_by_number(self, client, gm_token, player_token, table):
        url = f"/campaigns/{table['id']}/sessions"
        for _ in range(3):
            await client.post(url, json={}, headers=auth(gm_token))

        second_page = (await client.get(url, params={"page": 2, "size": 2}, headers=auth(player_token))).json()
        past_the_end = (await client.get(url, params={"page": 5, "size": 2}, headers=auth(player_token))).json()

        assert [row["number"] for row in second_page["items"]] == [3]
        assert (second_page["total"], second_page["page"], second_page["size"]) == (3, 2, 2)
        assert (past_the_end["items"], past_the_end["total"]) == ([], 3)

    async def test_status_filter_gives_the_archive(self, client, gm_token, player_token, table):
        url = f"/campaigns/{table['id']}/sessions"
        played = (await client.post(url, json={"status": "played"}, headers=auth(gm_token))).json()
        await client.post(url, json={}, headers=auth(gm_token))

        archive = await client.get(url, params={"status": "played"}, headers=auth(player_token))

        assert [row["id"] for row in archive.json()["items"]] == [played["id"]]

    async def test_published_chronicle_hides_gm_blocks_from_players(self, client, gm_token, player_token, table):
        created = await client.post(
            f"/campaigns/{table['id']}/sessions", json={"chronicle_markdown": CHRONICLE}, headers=auth(gm_token)
        )
        url = f"/campaigns/{table['id']}/sessions/{created.json()['id']}"
        await client.post(url + "/publish", headers=auth(gm_token))

        as_player = await client.get(url, headers=auth(player_token))
        as_gm = await client.get(url, headers=auth(gm_token))

        assert "keeper is already dead" not in as_player.json()["chronicle_markdown"]
        assert "They camped outside." in as_player.json()["chronicle_markdown"]
        assert as_gm.json()["chronicle_markdown"] == CHRONICLE

    async def test_numbers_increase_and_duplicates_conflict(self, client, gm_token, table):
        url = f"/campaigns/{table['id']}/sessions"
        await client.post(url, json={}, headers=auth(gm_token))
        second = await client.post(url, json={}, headers=auth(gm_token))
        duplicate = await client.post(url, json={"number": 2}, headers=auth(gm_token))

        assert second.json()["number"] == 2
        assert duplicate.status_code == 409

    async def test_players_cannot_write_sessions(self, client, player_token, table):
        response = await client.post(f"/campaigns/{table['id']}/sessions", json={}, headers=auth(player_token))

        assert response.status_code == 403


async def _participation_id(client, campaign_id, gm_token):
    roster = await client.get(f"/campaigns/{campaign_id}/characters", headers=auth(gm_token))
    return roster.json()["items"][0]["id"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestAttendance:
    async def test_gm_marks_who_attended_and_the_table_sees_it(self, client, gm_token, player_token, table):
        session = (await client.post(f"/campaigns/{table['id']}/sessions", json={}, headers=auth(gm_token))).json()
        participation_id = await _participation_id(client, table["id"], gm_token)
        url = f"/campaigns/{table['id']}/sessions/{session['id']}/attendance"

        marked = await client.put(url, json={"participation_ids": [participation_id]}, headers=auth(gm_token))
        player_list = await client.get(f"/campaigns/{table['id']}/sessions", headers=auth(player_token))
        cleared = await client.put(url, json={"participation_ids": []}, headers=auth(gm_token))

        assert marked.status_code == 200, marked.text
        attendee = marked.json()["attendees"][0]
        assert (attendee["participation_id"], attendee["character_name"]) == (participation_id, "Gurn")
        assert player_list.json()["items"][0]["attendees"] == marked.json()["attendees"]
        assert cleared.json()["attendees"] == []

    async def test_an_id_that_is_not_a_participation_here_is_400(self, client, gm_token, table):
        session = (await client.post(f"/campaigns/{table['id']}/sessions", json={}, headers=auth(gm_token))).json()
        url = f"/campaigns/{table['id']}/sessions/{session['id']}/attendance"

        response = await client.put(url, json={"participation_ids": [999_999]}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_players_cannot_mark_attendance(self, client, gm_token, player_token, table):
        session = (await client.post(f"/campaigns/{table['id']}/sessions", json={}, headers=auth(gm_token))).json()
        participation_id = await _participation_id(client, table["id"], gm_token)

        response = await client.put(
            f"/campaigns/{table['id']}/sessions/{session['id']}/attendance",
            json={"participation_ids": [participation_id]},
            headers=auth(player_token),
        )

        assert response.status_code == 403


async def _schedule_sessions(client, gm_token, campaign_id):
    """Two upcoming sessions (March created first), a past, an undated and a cancelled one: ``{key: id}``."""

    url = f"/campaigns/{campaign_id}/sessions"
    created = {}
    for key, payload in (
        ("march", {"title": "March", "scheduled_at": "2099-03-01T18:00:00Z"}),
        ("january", {"title": "January", "scheduled_at": "2099-01-01T18:00:00Z"}),
        ("past", {"title": "Past", "scheduled_at": "2000-01-01T18:00:00Z"}),
        ("undated", {"title": "Undated"}),
        ("cancelled", {"title": "Cancelled", "scheduled_at": "2099-02-01T18:00:00Z", "status": "cancelled"}),
    ):
        response = await client.post(url, json=payload, headers=auth(gm_token))
        assert response.status_code == 201, response.text
        created[key] = response.json()["id"]
    return created


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedule:
    async def test_upcoming_sessions_of_my_campaigns_soonest_first(
        self, client, gm_token, player_token, other_gm_token, table
    ):
        created = await _schedule_sessions(client, gm_token, table["id"])

        as_player = await client.get("/campaigns/schedule", headers=auth(player_token))
        as_gm = await client.get("/campaigns/schedule", headers=auth(gm_token))
        as_other_gm = await client.get("/campaigns/schedule", headers=auth(other_gm_token))
        with_cancelled = await client.get(
            "/campaigns/schedule", params={"include_cancelled": "true"}, headers=auth(player_token)
        )

        assert as_player.status_code == 200, as_player.text
        assert [row["id"] for row in as_player.json()["items"]] == [created["january"], created["march"]]
        assert {row["viewer_role"] for row in as_player.json()["items"]} == {"player"}
        assert as_player.json()["items"][0]["campaign"] == {"id": table["id"], "title": table["title"]}
        assert {row["viewer_role"] for row in as_gm.json()["items"]} == {"gm"}
        assert as_other_gm.json()["items"] == []
        assert [row["id"] for row in with_cancelled.json()["items"]] == [
            created["january"],
            created["cancelled"],
            created["march"],
        ]

    async def test_window_bounds(self, client, gm_token, player_token, table):
        created = await _schedule_sessions(client, gm_token, table["id"])

        until_february = await client.get(
            "/campaigns/schedule", params={"until": "2099-02-01T00:00:00Z"}, headers=auth(player_token)
        )
        from_the_past = await client.get(
            "/campaigns/schedule", params={"from": "1999-01-01T00:00:00Z"}, headers=auth(player_token)
        )

        assert [row["id"] for row in until_february.json()["items"]] == [created["january"]]
        assert from_the_past.json()["items"][0]["id"] == created["past"]
        assert from_the_past.json()["total"] == 3

    async def test_role_splits_the_gm_and_the_player_calendar(self, client, gm_token, player_token, table):
        created = await _schedule_sessions(client, gm_token, table["id"])

        gm_as_player = await client.get("/campaigns/schedule", params={"role": "player"}, headers=auth(gm_token))
        gm_as_gm = await client.get("/campaigns/schedule", params={"role": "gm"}, headers=auth(gm_token))
        player_as_gm = await client.get("/campaigns/schedule", params={"role": "gm"}, headers=auth(player_token))

        assert gm_as_player.json()["items"] == []
        assert [row["id"] for row in gm_as_gm.json()["items"]] == [created["january"], created["march"]]
        assert player_as_gm.json()["items"] == []

    async def test_archived_campaign_drops_out(self, client, gm_token, player_token, table):
        await _schedule_sessions(client, gm_token, table["id"])
        await client.post(f"/campaigns/{table['id']}/archive", headers=auth(gm_token))

        response = await client.get("/campaigns/schedule", headers=auth(player_token))

        assert response.json()["items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestNotes:
    async def test_notes_are_the_gms_only(self, client, gm_token, player_token, other_gm_token, table):
        created = await client.post(
            f"/campaigns/{table['id']}/notes", json={"title": "Cult", "body_markdown": "Mayor"}, headers=auth(gm_token)
        )

        as_player = await client.get(f"/campaigns/{table['id']}/notes", headers=auth(player_token))
        as_other_gm = await client.get(f"/campaigns/{table['id']}/notes", headers=auth(other_gm_token))
        as_gm = await client.get(f"/campaigns/{table['id']}/notes", headers=auth(gm_token))

        assert created.status_code == 201
        assert as_player.status_code == 403
        assert as_other_gm.status_code == 404
        assert [note["title"] for note in as_gm.json()["items"]] == ["Cult"]
