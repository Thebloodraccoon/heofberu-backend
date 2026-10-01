"""Input bounds on the race endpoints: malformed payloads fail with 422 instead of reaching the database."""

import pytest

INT32_OVERFLOW = 2_147_483_648


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceCreateValidation:
    @pytest.mark.parametrize("name", ["", "   ", "x" * 101])
    async def test_bad_name_returns_422(self, client, gm_token, name):
        response = await client.post("/races", json={"name": name}, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 422

    async def test_overlong_name_is_a_validation_error_not_a_server_error(self, client, gm_token):
        response = await client.post(
            "/races", json={"name": "x" * 500}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422
        assert "name" in response.text

    @pytest.mark.parametrize("speed", [-1, 201, 10**9])
    async def test_speed_out_of_range_returns_422(self, client, gm_token, speed):
        response = await client.post(
            "/races", json={"name": "Elf", "speed": speed}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422

    async def test_name_is_trimmed_and_boundary_values_are_accepted(self, client, gm_token):
        response = await client.post(
            "/races",
            json={"name": f"  {'x' * 100}  ", "speed": 0},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "x" * 100
        assert response.json()["speed"] == 0

    async def test_image_url_in_the_payload_is_ignored(self, client, gm_token):
        response = await client.post(
            "/races",
            json={"name": "Elf", "image_url": "https://evil.example/x.png"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["image_url"] is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceUpdateValidation:
    @pytest.mark.parametrize("field", ["name", "size", "speed", "description"])
    async def test_explicit_null_returns_422(self, client, gm_token, create_race, field):
        race = await create_race(name="Elf")

        response = await client.patch(
            f"/races/{race.id}", json={field: None}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("payload", [{"name": ""}, {"name": "x" * 101}, {"speed": -5}, {"speed": 999}])
    async def test_out_of_bounds_returns_422(self, client, gm_token, create_race, payload):
        race = await create_race(name="Elf")

        response = await client.patch(
            f"/races/{race.id}", json=payload, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422

    async def test_image_url_cannot_be_set_through_patch(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.patch(
            f"/races/{race.id}",
            json={"image_url": "https://evil.example/x.png", "description": "ok"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["image_url"] is None
        assert response.json()["description"] == "ok"

    async def test_duplicate_name_returns_400_as_declared(self, client, gm_token, create_race):
        await create_race(name="Elf")
        other = await create_race(name="Dwarf")

        response = await client.patch(
            f"/races/{other.id}", json={"name": "Elf"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceCapabilityBounds:
    async def test_bonus_outside_range_returns_422(self, client, gm_token, create_race):
        race = await create_race(name="Elf")
        headers = {"Authorization": f"Bearer {gm_token}"}

        for bonus in (11, -11, 10**9):
            response = await client.put(
                f"/races/{race.id}/ability-bonuses",
                json={"ability_bonuses": [{"ability": "DEX", "bonus": bonus}]},
                headers=headers,
            )
            assert response.status_code == 422

    async def test_negative_bonus_within_range_is_allowed(self, client, gm_token, create_race):
        race = await create_race(name="Orc")

        response = await client.put(
            f"/races/{race.id}/ability-bonuses",
            json={"ability_bonuses": [{"ability": "INT", "bonus": -2}, {"ability": "STR", "bonus": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {(b["ability"], b["bonus"]) for b in response.json()["ability_bonuses"]} == {("INT", -2), ("STR", 2)}

    async def test_more_bonuses_than_abilities_returns_422(self, client, gm_token, create_race):
        race = await create_race(name="Elf")
        items = [{"ability": a, "bonus": 1} for a in ("STR", "DEX", "CON", "INT", "WIS", "CHA")] * 2

        response = await client.put(
            f"/races/{race.id}/ability-bonuses",
            json={"ability_bonuses": items},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("ids", [[0], [-1], [INT32_OVERFLOW], [1, 1], list(range(1, 102))])
    async def test_skill_ids_out_of_bounds_return_422(self, client, gm_token, create_race, ids):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/skills", json={"skill_ids": ids}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("ids", [[0], [-1], [INT32_OVERFLOW], [2, 2], list(range(1, 102))])
    async def test_tag_ids_out_of_bounds_return_422(self, client, gm_token, create_race, ids):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/tags", json={"tag_ids": ids}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 422

    async def test_unknown_skill_ids_still_return_400(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/skills", json={"skill_ids": [987654]}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 400

    async def test_unknown_tag_ids_return_400(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/tags", json={"tag_ids": [987654]}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestPathIds:
    @pytest.mark.parametrize("path", ["/races/{}", "/races/{}/features", "/subraces/{}", "/subraces/{}/features"])
    async def test_ids_beyond_int32_return_422_not_500(self, client, path):
        response = await client.get(path.format(INT32_OVERFLOW))

        assert response.status_code == 422

    async def test_race_id_zero_is_rejected(self, client):
        assert (await client.get("/races/0")).status_code == 422

    async def test_subrace_list_race_id_bounds(self, client):
        assert (await client.get(f"/subraces?race_id={INT32_OVERFLOW}")).status_code == 422
        assert (await client.get("/subraces?race_id=0")).status_code == 422
        assert (await client.get("/subraces?race_id=999999")).status_code == 404
