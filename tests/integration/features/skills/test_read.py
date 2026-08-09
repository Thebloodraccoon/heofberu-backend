"""Tests for the skill read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestSkillOpenRead:
    async def test_list_skills(self, client, create_skill):
        await create_skill(key="ACROBATICS", name="Acrobatics", ability="DEX")
        await create_skill(key="ANIMAL_HANDLING", name="Animal Handling", ability="WIS")

        response = await client.get("/skills")

        assert response.status_code == 200
        keys = {item["key"] for item in response.json()["items"]}
        assert {"ACROBATICS", "ANIMAL_HANDLING"} <= keys

    async def test_list_skills_filters_by_ability_and_search(self, client, create_skill):
        await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        await create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = await client.get("/skills?ability=STR")

        assert response.status_code == 200
        assert all(item["ability"] == "STR" for item in response.json()["items"])

        search_response = await client.get("/skills?search=arcana")
        assert [item["key"] for item in search_response.json()["items"]] == ["ARCANA"]

    async def test_get_skill_by_id(self, client, create_skill):
        skill = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")

        response = await client.get(f"/skills/{skill.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Perception"
        assert response.json()["ability"] == "WIS"

    async def test_get_skill_404(self, client):
        assert (await client.get("/skills/999999")).status_code == 404
