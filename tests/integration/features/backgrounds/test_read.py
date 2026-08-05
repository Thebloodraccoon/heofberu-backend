"""Tests for the background read endpoints."""

import pytest


@pytest.mark.integration
class TestBackgroundOpenRead:
    def test_list_backgrounds(self, client, create_background):
        create_background(name="Acolyte")
        create_background(name="Criminal")

        response = client.get("/backgrounds/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Acolyte", "Criminal"} <= names

    def test_get_background_by_id(self, client, create_background):
        background = create_background(name="Acolyte")

        response = client.get(f"/backgrounds/{background.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Acolyte"

    def test_get_background_404(self, client):
        assert client.get("/backgrounds/999999").status_code == 404
