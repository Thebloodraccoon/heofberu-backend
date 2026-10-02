"""Tests for token subjects, refresh rotation, session revocation and email normalisation."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.core.email.dependencies import get_email_service
from app.core.security.token import create_access_token, create_reset_token, decode_token
from app.features.auth.schemas import ResetPasswordRequest
from app.features.auth.service import AuthService
from app.features.auth.sessions import claim_token, release_token
from app.main import app
from app.settings import settings


class FakeEmailService:
    """Records the reset emails instead of talking to SMTP."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_password_reset(self, to_email: str, reset_token: str) -> bool:
        self.sent.append((to_email, reset_token))
        return True


@pytest.fixture
def fake_email():
    service = FakeEmailService()
    app.dependency_overrides[get_email_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_email_service, None)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def reset(client, token: str, password: str = "new-password-456"):
    return await client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": password, "confirm_password": password},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTokenSubject:
    async def test_login_token_subject_is_the_user_id(self, client, create_user):
        user = await create_user(email="subject@example.com")
        response = await client.post("/auth/login", json={"email": user.email, "password": "password123"})

        assert decode_token(response.json()["access_token"])["sub"] == str(user.id)

    async def test_token_survives_email_change(self, client, player, player_token):
        response = await client.put("/users/me", json={"email": "moved@example.com"}, headers=bearer(player_token))
        assert response.status_code == 200

        me = await client.get("/users/me", headers=bearer(player_token))

        assert me.status_code == 200
        assert me.json()["email"] == "moved@example.com"

    async def test_refresh_survives_email_change(self, client, create_user):
        user = await create_user(email="before@example.com")
        login = await client.post("/auth/login", json={"email": user.email, "password": "password123"})
        token = login.json()["access_token"]
        await client.put("/users/me", json={"email": "after@example.com"}, headers=bearer(token))

        assert (await client.post("/auth/refresh")).status_code == 200

    async def test_legacy_email_subject_is_still_accepted(self, client, player):
        legacy = create_access_token({"sub": player.email})

        response = await client.get("/users/me", headers=bearer(legacy))

        assert response.status_code == 200
        assert response.json()["id"] == player.id

    async def test_unknown_subject_is_401(self, client):
        for subject in ("999999", "ghost@example.com", "garbage", "99999999999999999999"):
            response = await client.get("/users/me", headers=bearer(create_access_token({"sub": subject})))
            assert response.status_code == 401, subject

    async def test_deleted_user_token_is_401_not_404(self, client, create_user, founder_token, login_as):
        victim = await create_user(email="victim-token@example.com")
        victim_token = await login_as(victim)
        assert (await client.get("/users/me", headers=bearer(victim_token))).status_code == 200

        deleted = await client.delete(f"/users/{victim.id}", headers=bearer(founder_token))
        assert deleted.status_code == 204

        response = await client.get("/users/me", headers=bearer(victim_token))
        assert response.status_code == 401
        assert victim.email not in response.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoleCacheFreshness:
    async def test_promotion_and_demotion_apply_to_the_same_token_immediately(
        self, client, player, player_token, founder_token
    ):
        assert (await client.get("/users", headers=bearer(player_token))).status_code == 403

        promote = await client.put(f"/users/{player.id}", json={"role": "gm"}, headers=bearer(founder_token))
        assert promote.status_code == 200
        assert (await client.get("/users", headers=bearer(player_token))).status_code == 200

        demote = await client.put(f"/users/{player.id}", json={"role": "player"}, headers=bearer(founder_token))
        assert demote.status_code == 200
        assert (await client.get("/users", headers=bearer(player_token))).status_code == 403

    async def test_login_updates_last_login_in_the_cached_user(self, client, player):
        credentials = {"email": player.email, "password": "password123"}
        first_token = (await client.post("/auth/login", json=credentials)).json()["access_token"]
        first = (await client.get("/users/me", headers=bearer(first_token))).json()["last_login"]

        second_token = (await client.post("/auth/login", json=credentials)).json()["access_token"]
        second = (await client.get("/users/me", headers=bearer(second_token))).json()["last_login"]

        assert first is not None
        assert second > first


@pytest.mark.integration
@pytest.mark.asyncio
class TestEmailCase:
    async def test_register_stores_a_normalised_email(self, client, db_session):
        response = await client.post(
            "/auth/register",
            json={"username": "casey", "email": "  Casey@Example.COM ", "password": "password123"},
        )

        assert response.status_code == 201
        me = await client.get("/users/me", headers=bearer(response.json()["access_token"]))
        assert me.json()["email"] == "casey@example.com"

    async def test_register_rejects_the_same_email_in_another_case(self, client, create_user):
        await create_user(email="taken-case@example.com")

        response = await client.post(
            "/auth/register",
            json={"username": "copycat", "email": "Taken-Case@Example.com", "password": "password123"},
        )

        assert response.status_code == 400

    async def test_register_rejects_an_existing_mixed_case_email(self, client, create_user):
        await create_user(email="Legacy.Mixed@example.com")

        response = await client.post(
            "/auth/register",
            json={"username": "copycat2", "email": "legacy.mixed@example.com", "password": "password123"},
        )

        assert response.status_code == 400

    async def test_login_ignores_email_case(self, client, create_user):
        await create_user(email="login-case@example.com")

        response = await client.post("/auth/login", json={"email": "Login-Case@EXAMPLE.com", "password": "password123"})

        assert response.status_code == 200

    async def test_login_finds_a_legacy_mixed_case_account(self, client, create_user):
        await create_user(email="Old.Mixed@example.com")

        response = await client.post("/auth/login", json={"email": "old.mixed@example.com", "password": "password123"})

        assert response.status_code == 200

    async def test_forgot_password_ignores_email_case(self, client, create_user, fake_email):
        user = await create_user(email="forgot-case@example.com")

        response = await client.post("/auth/forgot-password", json={"email": "FORGOT-case@example.com"})

        assert response.status_code == 200
        assert [to for to, _ in fake_email.sent] == [user.email]

    async def test_user_cannot_change_email_to_another_users_email_in_another_case(
        self, client, create_user, player_token
    ):
        await create_user(email="occupied@example.com")

        response = await client.put("/users/me", json={"email": "Occupied@Example.com"}, headers=bearer(player_token))

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestRefreshRotation:
    async def test_refresh_issues_a_new_cookie_and_a_working_access_token(self, client, player):
        await client.post("/auth/login", json={"email": player.email, "password": "password123"})
        old_cookie = client.cookies.get("refresh_token")

        response = await client.post("/auth/refresh")

        assert response.status_code == 200
        assert client.cookies.get("refresh_token") != old_cookie
        assert (await client.get("/users/me", headers=bearer(response.json()["access_token"]))).status_code == 200

    async def test_a_refresh_token_works_only_once(self, client, player):
        await client.post("/auth/login", json={"email": player.email, "password": "password123"})
        old_cookie = client.cookies.get("refresh_token")
        assert (await client.post("/auth/refresh")).status_code == 200

        client.cookies.clear()
        replay = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={old_cookie}"})

        assert replay.status_code == 401

    async def test_the_rotated_cookie_keeps_working(self, client, player):
        await client.post("/auth/login", json={"email": player.email, "password": "password123"})

        assert (await client.post("/auth/refresh")).status_code == 200
        assert (await client.post("/auth/refresh")).status_code == 200

    async def test_refresh_after_logout_is_rejected(self, client, player):
        login = await client.post("/auth/login", json={"email": player.email, "password": "password123"})
        cookie = client.cookies.get("refresh_token")
        await client.post("/auth/logout", headers=bearer(login.json()["access_token"]))

        client.cookies.clear()
        response = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={cookie}"})

        assert response.status_code == 401

    async def test_refresh_for_a_deleted_user_is_rejected(self, client, create_user, founder_token):
        victim = await create_user(email="gone@example.com")
        await client.post("/auth/login", json={"email": victim.email, "password": "password123"})
        await client.delete(f"/users/{victim.id}", headers=bearer(founder_token))

        assert (await client.post("/auth/refresh")).status_code == 401

    async def test_an_access_token_is_not_a_refresh_token(self, client, player):
        access = create_access_token({"sub": str(player.id)})

        response = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={access}"})

        assert response.status_code == 401

    async def test_refresh_uses_the_first_of_duplicate_cookies(self, client, player):
        """The browser sends the current (longest-path) cookie first; a stale legacy one comes after it."""

        await client.post("/auth/login", json={"email": player.email, "password": "password123"})
        current = client.cookies.get("refresh_token")
        stale = create_access_token({"sub": str(player.id)})

        client.cookies.clear()
        cookie_header = f"refresh_token={current}; refresh_token={stale}"
        response = await client.post("/auth/refresh", headers={"Cookie": cookie_header})

        assert response.status_code == 200

    async def test_login_refresh_and_logout_expire_the_legacy_cookie_paths(self, client, player):
        def expires_legacy(response) -> bool:
            expired = {
                header.split("Path=")[1].split(";")[0]
                for header in response.headers.get_list("set-cookie")
                if "Max-Age=0" in header
            }
            return expired >= {"/api/auth", "/", "/api", "/api/v1"}

        login = await client.post("/auth/login", json={"email": player.email, "password": "password123"})
        refresh = await client.post("/auth/refresh")
        logout = await client.post("/auth/logout", headers=bearer(refresh.json()["access_token"]))

        assert expires_legacy(login) and expires_legacy(refresh) and expires_legacy(logout)


@pytest.mark.integration
@pytest.mark.asyncio
class TestPasswordResetRevokesSessions:
    async def test_reset_invalidates_existing_access_and_refresh_tokens(self, client, create_user):
        user = await create_user(email="revoked@example.com", password="old-password-123")
        login = await client.post("/auth/login", json={"email": user.email, "password": "old-password-123"})
        access = login.json()["access_token"]
        refresh_cookie = client.cookies.get("refresh_token")
        assert (await client.get("/users/me", headers=bearer(access))).status_code == 200

        response = await reset(client, create_reset_token({"sub": str(user.id)}))
        assert response.status_code == 200

        assert (await client.get("/users/me", headers=bearer(access))).status_code == 401
        client.cookies.clear()
        refresh = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={refresh_cookie}"})
        assert refresh.status_code == 401

    async def test_logging_in_after_a_reset_works(self, client, create_user):
        user = await create_user(email="relogin@example.com", password="old-password-123")
        await reset(client, create_reset_token({"sub": str(user.id)}))

        login = await client.post("/auth/login", json={"email": user.email, "password": "new-password-456"})

        assert login.status_code == 200
        me = await client.get("/users/me", headers=bearer(login.json()["access_token"]))
        assert me.status_code == 200
        assert (await client.post("/auth/refresh")).status_code == 200

    async def test_reset_does_not_touch_other_users(self, client, create_user, player, player_token):
        user = await create_user(email="other-reset@example.com")

        await reset(client, create_reset_token({"sub": str(user.id)}))

        assert (await client.get("/users/me", headers=bearer(player_token))).status_code == 200

    async def test_reset_token_with_a_legacy_email_subject_still_works(self, client, create_user):
        user = await create_user(email="legacy-reset@example.com", password="old-password-123")

        response = await reset(client, create_reset_token({"sub": user.email}))

        assert response.status_code == 200

    async def test_an_older_reset_link_dies_after_a_newer_one_was_used(self, client, create_user):
        user = await create_user(email="two-links@example.com", password="old-password-123")
        older = create_reset_token({"sub": str(user.id)})
        await asyncio.sleep(0.01)
        newer = create_reset_token({"sub": str(user.id)})

        assert (await reset(client, newer)).status_code == 200
        assert (await reset(client, older, "third-password-789")).status_code == 400

    async def test_access_token_cannot_be_used_as_a_reset_token(self, client, create_user):
        user = await create_user(email="wrong-type@example.com")

        response = await reset(client, create_access_token({"sub": str(user.id)}))

        assert response.status_code == 400

    async def test_reset_for_a_deleted_user_is_rejected(self, client):
        response = await reset(client, create_reset_token({"sub": "999999"}))

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestResetTokenIsSingleUse:
    async def test_claim_is_atomic_under_concurrency(self, redis_client):
        results = await asyncio.gather(*[claim_token("jti-race-1", 60, reason="test") for _ in range(8)])

        assert results.count(True) == 1
        await redis_client.delete("token_blacklist:jti-race-1")

    async def test_claim_can_be_released(self, redis_client):
        assert await claim_token("jti-release-1", 60, reason="test") is True
        assert await claim_token("jti-release-1", 60, reason="test") is False

        await release_token("jti-release-1")

        assert await claim_token("jti-release-1", 60, reason="test") is True
        await redis_client.delete("token_blacklist:jti-release-1")

    async def test_expired_token_cannot_be_claimed(self):
        assert await claim_token("jti-expired", 0, reason="test") is False

    async def test_a_token_claimed_elsewhere_is_rejected(self, client, create_user):
        user = await create_user(email="preclaimed@example.com")
        token = create_reset_token({"sub": str(user.id)})
        jti = decode_token(token)["jti"]
        assert await claim_token(jti, 60, reason="test") is True

        assert (await reset(client, token)).status_code == 400

    async def test_a_failed_update_releases_the_token_for_a_retry(self, db_session, create_user, monkeypatch):
        user = await create_user(email="retry@example.com", password="old-password-123")
        token = create_reset_token({"sub": str(user.id)})
        service = AuthService(db_session, FakeEmailService())
        request = ResetPasswordRequest(
            token=token, new_password="new-password-456", confirm_password="new-password-456"
        )

        async def boom(_user_id):
            raise RuntimeError("redis write failed")

        monkeypatch.setattr("app.features.auth.service.revoke_user_sessions", boom)
        with pytest.raises(RuntimeError):
            await service.reset_password(request)
        monkeypatch.undo()

        result = await service.reset_password(request)

        assert result.detail.startswith("Password has been reset")


@pytest.mark.integration
@pytest.mark.asyncio
class TestForgotPasswordIsBackgrounded:
    async def test_email_is_queued_not_sent_inline(self, db_session, create_user):
        from fastapi import BackgroundTasks

        from app.features.auth.schemas import ForgotPasswordRequest

        user = await create_user(email="queued@example.com")
        email = FakeEmailService()
        tasks = BackgroundTasks()

        response = await AuthService(db_session, email).forgot_password(ForgotPasswordRequest(email=user.email), tasks)

        assert "reset link has been sent" in response.detail
        assert email.sent == []
        assert len(tasks.tasks) == 1

        await tasks()
        assert [to for to, _ in email.sent] == [user.email]

    async def test_unknown_account_queues_nothing_and_answers_identically(self, db_session):
        from fastapi import BackgroundTasks

        from app.features.auth.schemas import ForgotPasswordRequest

        tasks = BackgroundTasks()

        response = await AuthService(db_session, FakeEmailService()).forgot_password(
            ForgotPasswordRequest(email="nobody@example.com"), tasks
        )

        assert "reset link has been sent" in response.detail
        assert tasks.tasks == []

    async def test_reset_link_from_the_email_works(self, client, create_user, fake_email):
        user = await create_user(email="link@example.com", password="old-password-123")
        await client.post("/auth/forgot-password", json={"email": user.email})
        (_, token) = fake_email.sent[0]

        assert decode_token(token)["sub"] == str(user.id)
        assert (await reset(client, token)).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisOutage:
    async def test_authenticated_request_fails_closed_with_503(self, client, player_token, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("redis is down")
            yield

        monkeypatch.setattr(settings, "get_auth_redis", lambda: broken_redis())

        response = await client.get("/users/me", headers=bearer(player_token))

        assert response.status_code == 503
        assert "redis is down" not in response.text

    async def test_refresh_fails_closed_with_503(self, client, player, monkeypatch):
        await client.post("/auth/login", json={"email": player.email, "password": "password123"})

        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("redis is down")
            yield

        monkeypatch.setattr(settings, "get_auth_redis", lambda: broken_redis())

        assert (await client.post("/auth/refresh")).status_code == 503


@pytest.mark.integration
@pytest.mark.asyncio
class TestBadInput:
    async def test_register_rejects_overlong_password(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "longpw", "email": "longpw@example.com", "password": "a" * 73},
        )

        assert response.status_code == 400

    async def test_register_accepts_a_72_byte_password(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "maxpw", "email": "maxpw@example.com", "password": "a" * 72},
        )

        assert response.status_code == 201

    async def test_login_rejects_absurdly_long_password_without_hashing_it(self, client):
        response = await client.post("/auth/login", json={"email": "x@example.com", "password": "a" * 5000})

        assert response.status_code == 422

    async def test_refresh_token_cookie_is_rotated_per_login(self, client, player):
        first = await client.post("/auth/login", json={"email": player.email, "password": "password123"})
        first_cookie = first.cookies.get("refresh_token")
        second = await client.post("/auth/login", json={"email": player.email, "password": "password123"})

        assert second.cookies.get("refresh_token") != first_cookie
        assert decode_token(first_cookie)["token_type"] == "refresh"
