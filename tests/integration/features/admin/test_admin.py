"""Tests for the admin (found-father-only) endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestAdminCache:
    async def test_flush_cache_requires_founder(self, client, player_token, gm_token):
        for token in (player_token, gm_token):
            response = await client.delete("/admin/cache", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 403

    async def test_flush_cache_as_founder_returns_204(self, client, founder_token, redis_client):
        response = await client.delete("/admin/cache", headers={"Authorization": f"Bearer {founder_token}"})
        assert response.status_code == 204

    async def test_flush_cache_requires_auth(self, client):
        response = await client.delete("/admin/cache")
        assert response.status_code == 401
