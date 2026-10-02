"""The cached auth user (``users:get_auth_user``) must never outlive a role change, a delete or a profile edit."""

from contextlib import asynccontextmanager

import pytest

import app.core.cache.client as cache_client
from app.features.users.service import user_cache_key
from app.settings import settings


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def caching_on(monkeypatch, redis_client):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    return redis_client


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthUserCache:
    async def test_an_authenticated_request_populates_the_exact_key_the_invalidator_targets(
        self, client, player, player_token, caching_on
    ):
        await client.get("/users/me", headers=bearer(player_token))

        assert await caching_on.exists(user_cache_key(player.id)) == 1

    async def test_demoted_gm_loses_gm_rights_on_the_next_request(
        self, client, gm, gm_token, founder_token, caching_on
    ):
        assert (await client.get("/users", headers=bearer(gm_token))).status_code == 200
        assert await caching_on.exists(user_cache_key(gm.id)) == 1

        changed = await client.put(f"/users/{gm.id}", json={"role": "player"}, headers=bearer(founder_token))

        assert changed.status_code == 200, changed.text
        assert await caching_on.exists(user_cache_key(gm.id)) == 0
        assert (await client.get("/users", headers=bearer(gm_token))).status_code == 403
        assert (await client.get("/users/me", headers=bearer(gm_token))).json()["role"] == "player"

    async def test_promoted_player_gets_gm_rights_on_the_next_request(
        self, client, player, player_token, founder_token, caching_on
    ):
        assert (await client.get("/users", headers=bearer(player_token))).status_code == 403

        await client.put(f"/users/{player.id}", json={"role": "gm"}, headers=bearer(founder_token))

        assert (await client.get("/users", headers=bearer(player_token))).status_code == 200

    async def test_deleted_user_is_rejected_on_the_next_request(
        self, client, player, player_token, founder_token, caching_on
    ):
        assert (await client.get("/users/me", headers=bearer(player_token))).status_code == 200

        deleted = await client.delete(f"/users/{player.id}", headers=bearer(founder_token))

        assert deleted.status_code == 204
        assert await caching_on.exists(user_cache_key(player.id)) == 0
        assert (await client.get("/users/me", headers=bearer(player_token))).status_code == 401

    async def test_profile_edit_is_visible_at_once(self, client, player_token, caching_on):
        assert (await client.get("/users/me", headers=bearer(player_token))).json()["bio"] in (None, "")

        edited = await client.put("/users/me", json={"bio": "Keeper of lore"}, headers=bearer(player_token))

        assert edited.status_code == 200
        assert (await client.get("/users/me", headers=bearer(player_token))).json()["bio"] == "Keeper of lore"

    async def test_admin_edit_of_another_user_refreshes_that_users_cached_record(
        self, client, player, player_token, gm_token, caching_on
    ):
        await client.get("/users/me", headers=bearer(player_token))

        await client.put(f"/users/{player.id}", json={"bio": "Edited by GM"}, headers=bearer(gm_token))

        assert (await client.get("/users/me", headers=bearer(player_token))).json()["bio"] == "Edited by GM"

    async def test_login_refreshes_the_cached_last_login(self, client, player, login_as, caching_on):
        first_token = await login_as(player)
        first = (await client.get("/users/me", headers=bearer(first_token))).json()["last_login"]

        second_token = await login_as(player)
        second = (await client.get("/users/me", headers=bearer(second_token))).json()["last_login"]

        assert first is not None
        assert second > first

    async def test_failed_update_keeps_the_cached_record(self, client, player, player_token, gm_token, caching_on):
        await client.get("/users/me", headers=bearer(player_token))

        response = await client.put(f"/users/{player.id}", json={"email": "not-an-email"}, headers=bearer(gm_token))

        assert response.status_code in (400, 422)
        assert await caching_on.exists(user_cache_key(player.id)) == 1

    async def test_deleting_an_author_refreshes_their_cached_articles(
        self, client, create_user, create_article, founder_token, gm_token, caching_on
    ):
        from app.features.articles.cache import article_cache_key

        article = await create_article(title="Authored", status="published")
        await client.get(f"/articles/{article['id']}")
        assert await caching_on.exists(article_cache_key(article["id"])) == 1
        author_id = article["author"]["id"]

        deleted = await client.delete(f"/users/{author_id}", headers=bearer(founder_token))

        assert deleted.status_code == 204
        assert await caching_on.exists(article_cache_key(article["id"])) == 0
        assert (await client.get(f"/articles/{article['id']}")).json()["author"] is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisOutageDuringInvalidation:
    async def test_role_change_made_while_redis_is_down_is_never_served_stale_afterwards(
        self, client, gm, gm_token, founder_token, caching_on, monkeypatch
    ):
        state = {"down": False}
        real_provider = settings.get_redis

        @asynccontextmanager
        async def flaky():
            if state["down"]:
                raise ConnectionError("redis down")
            async with real_provider() as redis:
                yield redis

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: flaky)
        assert (await client.get("/users", headers=bearer(gm_token))).status_code == 200
        assert await caching_on.exists(user_cache_key(gm.id)) == 1

        state["down"] = True
        changed = await client.put(f"/users/{gm.id}", json={"role": "player"}, headers=bearer(founder_token))
        assert changed.status_code == 200, changed.text

        state["down"] = False
        cache_client._breaker.success()

        assert (await client.get("/users", headers=bearer(gm_token))).status_code == 403
        assert await caching_on.exists(user_cache_key(gm.id)) == 1
        cache_client._pending.clear()
