"""Tests for the health-check endpoint."""

import pytest


@pytest.mark.integration
def test_ping_returns_healthy(client):
    response = client.get("/ping")

    assert response.status_code == 200
    body = response.json()
    assert body["ping"] == "pong"
    assert body["status"] == "healthy"
    assert isinstance(body["timestamp"], float)
