"""Smoke tests for PUT .../tags on races, backgrounds and subraces (same shared-tags pattern as articles)."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceTags:
    async def test_gm_can_set_race_tags(self, client, gm_token, create_race):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Elven"}, headers=headers)).json()
        race = await create_race(name="Elf")

        response = await client.put(f"/races/{race.id}/tags", json={"tag_ids": [tag["id"]]}, headers=headers)

        assert response.status_code == 200
        assert [t["name"] for t in response.json()["tags"]] == ["Elven"]

    async def test_player_cannot_set_race_tags(self, client, player_token, create_race):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/tags",
            json={"tag_ids": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackgroundTags:
    async def test_gm_can_set_background_tags(self, client, gm_token, create_background):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Criminal"}, headers=headers)).json()
        background = await create_background(name="Charlatan", with_suggestions=False)

        response = await client.put(
            f"/backgrounds/{background.id}/tags", json={"tag_ids": [tag["id"]]}, headers=headers
        )

        assert response.status_code == 200
        assert [t["name"] for t in response.json()["tags"]] == ["Criminal"]

    async def test_player_cannot_set_background_tags(self, client, player_token, create_background):
        background = await create_background(name="Charlatan", with_suggestions=False)

        response = await client.put(
            f"/backgrounds/{background.id}/tags",
            json={"tag_ids": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceTags:
    async def test_gm_can_set_subrace_tags(self, client, gm_token, create_race, create_subrace):
        headers = {"Authorization": f"Bearer {gm_token}"}
        tag = (await client.post("/tags", json={"name": "Wood"}, headers=headers)).json()
        race = await create_race(name="Elf")
        subrace = await create_subrace(race.id, name="Wood Elf")

        response = await client.put(f"/subraces/{subrace.id}/tags", json={"tag_ids": [tag["id"]]}, headers=headers)

        assert response.status_code == 200
        assert [t["name"] for t in response.json()["tags"]] == ["Wood"]

    async def test_player_cannot_set_subrace_tags(self, client, player_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race.id, name="Wood Elf")

        response = await client.put(
            f"/subraces/{subrace.id}/tags",
            json={"tag_ids": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
