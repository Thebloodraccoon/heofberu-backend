"""Race deletion cascade, in-use guard, tag/skill replacement and cache freshness."""

import pytest

from app.settings import settings


@pytest.fixture
def caching_on(monkeypatch, redis_client):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 300)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceDeleteCascade:
    async def test_delete_removes_subraces_and_their_features(
        self, client, gm_token, founder_token, create_race, create_subrace, storage
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        race_feature = await client.post(
            "/features",
            json={"name": "Keen Senses", "source_type": "RACE", "race_id": race.id},
            headers=auth(gm_token),
        )
        subrace_feature = await client.post(
            "/features",
            json={"name": "Cantrip", "source_type": "SUBRACE", "subrace_id": subrace.id},
            headers=auth(gm_token),
        )
        assert race_feature.status_code == 201 and subrace_feature.status_code == 201

        response = await client.delete(f"/races/{race.id}", headers=auth(founder_token))

        assert response.status_code == 204
        assert (await client.get(f"/races/{race.id}")).status_code == 404
        assert (await client.get(f"/subraces/{subrace.id}")).status_code == 404
        assert (await client.get(f"/features/{race_feature.json()['id']}")).status_code == 404
        assert (await client.get(f"/features/{subrace_feature.json()['id']}")).status_code == 404

    async def test_delete_drops_race_and_subrace_images(
        self, client, founder_token, create_race, create_subrace, storage
    ):
        race = await create_race(name="Elf")
        first = await create_subrace(race_id=race.id, name="High Elf")
        second = await create_subrace(race_id=race.id, name="Wood Elf")

        assert (await client.delete(f"/races/{race.id}", headers=auth(founder_token))).status_code == 204

        assert ("races", race.id) in storage.deleted
        assert {("subraces", first.id), ("subraces", second.id)} <= set(storage.deleted)

    async def test_delete_subrace_drops_its_image(self, client, founder_token, create_race, create_subrace, storage):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        assert (await client.delete(f"/subraces/{subrace.id}", headers=auth(founder_token))).status_code == 204

        assert storage.deleted == [("subraces", subrace.id)]

    async def test_race_with_character_on_one_of_its_subraces_cannot_be_deleted(
        self, client, founder_token, create_race, create_subrace, create_class, create_user, create_character, storage
    ):
        race = await create_race(name="Elf")
        other_race = await create_race(name="Human")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        player = await create_user()
        character_class = await create_class(name="Wizard")
        await create_character(
            owner_id=player.id, class_id=character_class.id, race_id=other_race.id, subrace_id=subrace.id
        )

        response = await client.delete(f"/races/{race.id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert storage.deleted == []
        assert (await client.get(f"/subraces/{subrace.id}")).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheFreshness:
    async def test_cascade_delete_does_not_leave_cached_subrace_reads(
        self, client, gm_token, founder_token, create_race, create_subrace, caching_on, storage
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        added = await client.post(
            "/features",
            json={"name": "Cantrip", "source_type": "SUBRACE", "subrace_id": subrace.id},
            headers=auth(gm_token),
        )
        feature_id = added.json()["id"]
        for url in (
            f"/races/{race.id}",
            f"/subraces/{subrace.id}",
            f"/subraces/{subrace.id}/features",
            f"/features/{feature_id}",
        ):
            assert (await client.get(url)).status_code == 200

        assert (await client.delete(f"/races/{race.id}", headers=auth(founder_token))).status_code == 204

        for url in (
            f"/races/{race.id}",
            f"/subraces/{subrace.id}",
            f"/subraces/{subrace.id}/features",
            f"/features/{feature_id}",
        ):
            assert (await client.get(url)).status_code == 404, url

    async def test_subrace_delete_does_not_leave_cached_reads(
        self, client, gm_token, founder_token, create_race, create_subrace, caching_on, storage
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        assert len((await client.get(f"/races/{race.id}")).json()["subraces"]) == 1
        assert (await client.get(f"/subraces/{subrace.id}")).status_code == 200

        assert (await client.delete(f"/subraces/{subrace.id}", headers=auth(founder_token))).status_code == 204

        assert (await client.get(f"/races/{race.id}")).json()["subraces"] == []
        assert (await client.get(f"/subraces/{subrace.id}")).status_code == 404

    async def test_subrace_changes_show_up_in_cached_race_detail(
        self, client, gm_token, create_race, create_subrace, caching_on
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        assert (await client.get(f"/races/{race.id}")).json()["subraces"][0]["name"] == "High Elf"
        assert (await client.get(f"/subraces/{subrace.id}")).json()["name"] == "High Elf"

        renamed = await client.patch(f"/subraces/{subrace.id}", json={"name": "Sun Elf"}, headers=auth(gm_token))

        assert renamed.status_code == 200
        assert (await client.get(f"/races/{race.id}")).json()["subraces"][0]["name"] == "Sun Elf"
        assert (await client.get(f"/subraces/{subrace.id}")).json()["name"] == "Sun Elf"

    async def test_ability_bonus_and_tag_changes_refresh_cached_subrace(
        self, client, gm_token, create_race, create_subrace, caching_on
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        tag = (await client.post("/tags", json={"name": "Elven"}, headers=auth(gm_token))).json()
        before = (await client.get(f"/subraces/{subrace.id}")).json()
        assert before["ability_bonuses"] == [] and before["tags"] == []

        await client.put(
            f"/subraces/{subrace.id}/ability-bonuses",
            json={"ability_bonuses": [{"ability": "INT", "bonus": 1}]},
            headers=auth(gm_token),
        )
        await client.put(f"/subraces/{subrace.id}/tags", json={"tag_ids": [tag["id"]]}, headers=auth(gm_token))

        after = (await client.get(f"/subraces/{subrace.id}")).json()
        assert after["ability_bonuses"] == [{"ability": "INT", "bonus": 1}]
        assert [t["name"] for t in after["tags"]] == ["Elven"]

    async def test_race_tag_assignment_refreshes_the_cached_tag_listing(
        self, client, gm_token, create_race, caching_on
    ):
        race = await create_race(name="Elf")
        tag = (await client.post("/tags", json={"name": "Elven"}, headers=auth(gm_token))).json()
        listing = await client.get("/tags", headers=auth(gm_token))
        assert listing.status_code == 200
        assert [t["usage_count"] for t in listing.json()["items"] if t["id"] == tag["id"]] == [0]

        await client.put(f"/races/{race.id}/tags", json={"tag_ids": [tag["id"]]}, headers=auth(gm_token))

        listing = await client.get("/tags", headers=auth(gm_token))
        assert [t["usage_count"] for t in listing.json()["items"] if t["id"] == tag["id"]] == [1]

    async def test_race_update_shows_up_in_cached_detail_and_listing(self, client, gm_token, create_race, caching_on):
        race = await create_race(name="Dwarf", speed=25)
        assert (await client.get(f"/races/{race.id}")).json()["speed"] == 25
        assert (await client.get("/races")).json()["items"][0]["name"] == "Dwarf"

        response = await client.patch(
            f"/races/{race.id}", json={"speed": 40, "name": "Hill Dwarf"}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert (await client.get(f"/races/{race.id}")).json()["speed"] == 40
        assert (await client.get("/races")).json()["items"][0]["name"] == "Hill Dwarf"


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceTagsAndSkills:
    async def test_tags_are_replaced_cleared_and_shown_on_read(self, client, gm_token, create_race):
        race = await create_race(name="Elf")
        headers = auth(gm_token)
        first = (await client.post("/tags", json={"name": "Elven"}, headers=headers)).json()
        second = (await client.post("/tags", json={"name": "Fey"}, headers=headers)).json()

        both = await client.put(
            f"/races/{race.id}/tags", json={"tag_ids": [first["id"], second["id"]]}, headers=headers
        )
        assert [t["name"] for t in both.json()["tags"]] == ["Elven", "Fey"]

        only_second = await client.put(f"/races/{race.id}/tags", json={"tag_ids": [second["id"]]}, headers=headers)
        assert [t["name"] for t in only_second.json()["tags"]] == ["Fey"]
        assert [t["name"] for t in (await client.get(f"/races/{race.id}")).json()["tags"]] == ["Fey"]

        cleared = await client.put(f"/races/{race.id}/tags", json={"tag_ids": []}, headers=headers)
        assert cleared.json()["tags"] == []

    async def test_duplicate_tag_ids_return_422(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.put(f"/races/{race.id}/tags", json={"tag_ids": [1, 1]}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_tags_for_missing_race_return_404(self, client, gm_token):
        response = await client.put("/races/987654/tags", json={"tag_ids": []}, headers=auth(gm_token))

        assert response.status_code == 404

    async def test_skills_are_replaced_and_cleared(self, client, gm_token, create_race, create_skill):
        race = await create_race(name="Elf")
        first = await create_skill(name="Perception")
        second = await create_skill(name="Stealth", ability="DEX")
        headers = auth(gm_token)

        both = await client.put(f"/races/{race.id}/skills", json={"skill_ids": [first.id, second.id]}, headers=headers)
        assert {s["name"] for s in both.json()["granted_skills"]} == {"Perception", "Stealth"}

        only_second = await client.put(f"/races/{race.id}/skills", json={"skill_ids": [second.id]}, headers=headers)
        assert [s["name"] for s in only_second.json()["granted_skills"]] == ["Stealth"]

        cleared = await client.put(f"/races/{race.id}/skills", json={"skill_ids": []}, headers=headers)
        assert cleared.json()["granted_skills"] == []

    async def test_player_cannot_set_skills(self, client, player_token, create_race):
        race = await create_race(name="Elf")

        response = await client.put(f"/races/{race.id}/skills", json={"skill_ids": []}, headers=auth(player_token))

        assert response.status_code == 403
