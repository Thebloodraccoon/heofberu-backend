"""Tests for the background read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackgroundOpenRead:
    async def test_list_backgrounds(self, client, create_background):
        await create_background(name="Acolyte")
        await create_background(name="Criminal")

        response = await client.get("/backgrounds/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Acolyte", "Criminal"} <= names

    async def test_get_background_by_id(self, client, create_background):
        background = await create_background(name="Acolyte")

        response = await client.get(f"/backgrounds/{background.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Acolyte"

    async def test_get_background_404(self, client):
        assert (await client.get("/backgrounds/999999")).status_code == 404
