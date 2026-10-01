"""Subrace rules: race-scoped name uniqueness, input bounds, tags, declared status codes."""

import pytest

from app import main as app_module


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceScopedNames:
    async def test_rename_to_a_name_used_in_another_race_succeeds(self, client, gm_token, create_race, create_subrace):
        elf = await create_race(name="Elf")
        dwarf = await create_race(name="Dwarf")
        await create_subrace(race_id=dwarf.id, name="Mountain")
        hill = await create_subrace(race_id=elf.id, name="Hill")

        response = await client.patch(f"/subraces/{hill.id}", json={"name": "Mountain"}, headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["name"] == "Mountain"
        assert response.json()["race_id"] == elf.id

    async def test_rename_to_a_sibling_name_returns_400(self, client, gm_token, create_race, create_subrace):
        elf = await create_race(name="Elf")
        await create_subrace(race_id=elf.id, name="High Elf")
        wood = await create_subrace(race_id=elf.id, name="Wood Elf")

        response = await client.patch(f"/subraces/{wood.id}", json={"name": "High Elf"}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_patch_keeping_the_same_name_succeeds(self, client, gm_token, create_race, create_subrace):
        elf = await create_race(name="Elf")
        high = await create_subrace(race_id=elf.id, name="High Elf")

        response = await client.patch(
            f"/subraces/{high.id}", json={"name": "High Elf", "description": "x"}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["description"] == "x"

    async def test_same_name_in_two_races_can_be_created(self, client, gm_token, create_race):
        elf = await create_race(name="Elf")
        dwarf = await create_race(name="Dwarf")

        first = await client.post("/subraces", json={"name": "Northern", "race_id": elf.id}, headers=auth(gm_token))
        second = await client.post("/subraces", json={"name": "Northern", "race_id": dwarf.id}, headers=auth(gm_token))

        assert first.status_code == second.status_code == 201

    async def test_same_name_in_the_same_race_is_rejected(self, client, gm_token, create_race, create_subrace):
        elf = await create_race(name="Elf")
        await create_subrace(race_id=elf.id, name="Northern")

        response = await client.post("/subraces", json={"name": "Northern", "race_id": elf.id}, headers=auth(gm_token))

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceValidation:
    @pytest.mark.parametrize("name", ["", "   ", "x" * 101, "y" * 500])
    async def test_create_with_bad_name_returns_422(self, client, gm_token, create_race, name):
        race = await create_race(name="Elf")

        response = await client.post("/subraces", json={"name": name, "race_id": race.id}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("race_id", [0, -1, 2_147_483_648])
    async def test_create_with_bad_race_id_returns_422(self, client, gm_token, race_id):
        response = await client.post("/subraces", json={"name": "High Elf", "race_id": race_id}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_name_boundary_values(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post("/subraces", json={"name": "x" * 100, "race_id": race.id}, headers=auth(gm_token))

        assert response.status_code == 201

    @pytest.mark.parametrize("payload", [{"name": None}, {"description": None}, {"name": ""}, {"name": "x" * 101}])
    async def test_patch_invalid_payload_returns_422(self, client, gm_token, create_race, create_subrace, payload):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.patch(f"/subraces/{subrace.id}", json=payload, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_bonus_out_of_range_returns_422(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        for bonus in (11, -11, 10**9):
            response = await client.put(
                f"/subraces/{subrace.id}/ability-bonuses",
                json={"ability_bonuses": [{"ability": "INT", "bonus": bonus}]},
                headers=auth(gm_token),
            )
            assert response.status_code == 422

    @pytest.mark.parametrize("ids", [[0], [-1], [2_147_483_648], [3, 3], list(range(1, 102))])
    async def test_tag_ids_out_of_bounds_return_422(self, client, gm_token, create_race, create_subrace, ids):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.put(f"/subraces/{subrace.id}/tags", json={"tag_ids": ids}, headers=auth(gm_token))

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceTags:
    async def test_tags_are_replaced_cleared_and_shown_on_read(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        first = (await client.post("/tags", json={"name": "Elven"}, headers=auth(gm_token))).json()
        second = (await client.post("/tags", json={"name": "Fey"}, headers=auth(gm_token))).json()

        both = await client.put(
            f"/subraces/{subrace.id}/tags", json={"tag_ids": [first["id"], second["id"]]}, headers=auth(gm_token)
        )
        assert [t["name"] for t in both.json()["tags"]] == ["Elven", "Fey"]

        one = await client.put(f"/subraces/{subrace.id}/tags", json={"tag_ids": [second["id"]]}, headers=auth(gm_token))
        assert [t["name"] for t in one.json()["tags"]] == ["Fey"]
        assert [t["name"] for t in (await client.get(f"/subraces/{subrace.id}")).json()["tags"]] == ["Fey"]

        cleared = await client.put(f"/subraces/{subrace.id}/tags", json={"tag_ids": []}, headers=auth(gm_token))
        assert cleared.json()["tags"] == []

    async def test_unknown_tag_ids_return_400(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        response = await client.put(f"/subraces/{subrace.id}/tags", json={"tag_ids": [987654]}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_tags_for_missing_subrace_return_404(self, client, gm_token):
        response = await client.put("/subraces/987654/tags", json={"tag_ids": []}, headers=auth(gm_token))

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceDetail:
    async def test_get_returns_bonuses_tags_and_features_together(self, client, gm_token, create_race, create_subrace):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        await client.put(
            f"/subraces/{subrace.id}/ability-bonuses",
            json={"ability_bonuses": [{"ability": "INT", "bonus": 1}]},
            headers=auth(gm_token),
        )
        await client.post(
            "/features",
            json={"name": "Cantrip", "source_type": "SUBRACE", "subrace_id": subrace.id},
            headers=auth(gm_token),
        )
        await client.post(
            "/features",
            json={"name": "Trance", "source_type": "SUBRACE", "subrace_id": subrace.id},
            headers=auth(gm_token),
        )

        body = (await client.get(f"/subraces/{subrace.id}")).json()
        listed = (await client.get(f"/subraces/{subrace.id}/features")).json()

        assert body["ability_bonuses"] == [{"ability": "INT", "bonus": 1}]
        assert [f["name"] for f in body["features"]] == ["Cantrip", "Trance"]
        assert [f["id"] for f in body["features"]] == [f["id"] for f in listed]

    async def test_create_and_update_responses_include_features_field(
        self, client, gm_token, create_race, create_subrace
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        await client.post(
            "/features",
            json={"name": "Cantrip", "source_type": "SUBRACE", "subrace_id": subrace.id},
            headers=auth(gm_token),
        )

        updated = await client.patch(f"/subraces/{subrace.id}", json={"description": "x"}, headers=auth(gm_token))

        assert [f["name"] for f in updated.json()["features"]] == ["Cantrip"]

    async def test_delete_in_use_subrace_returns_409(
        self, client, founder_token, create_race, create_subrace, create_class, create_user, create_character
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        player = await create_user()
        character_class = await create_class(name="Wizard")
        await create_character(owner_id=player.id, class_id=character_class.id, race_id=race.id, subrace_id=subrace.id)

        response = await client.delete(f"/subraces/{subrace.id}", headers=auth(founder_token))

        assert response.status_code == 409

    async def test_openapi_documents_the_codes_the_api_returns(self):
        paths = app_module.app.openapi()["paths"]
        paths = {path.removeprefix("/api/v1"): item for path, item in paths.items()}

        assert "400" in paths["/races"]["post"]["responses"]
        assert "409" not in paths["/races"]["post"]["responses"]
        assert "400" in paths["/races/{race_id}"]["patch"]["responses"]
        assert "400" in paths["/subraces"]["post"]["responses"]
        assert "400" in paths["/subraces/{subrace_id}"]["patch"]["responses"]
        assert "409" in paths["/subraces/{subrace_id}"]["delete"]["responses"]
        assert "400" not in paths["/subraces/{subrace_id}"]["delete"]["responses"]
