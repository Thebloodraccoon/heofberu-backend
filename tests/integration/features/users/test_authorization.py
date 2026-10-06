"""Tests for role/ownership guards and partial-update validation on the user endpoints."""

import pytest

from app.constants import UserRole
from app.settings import settings


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoleEscalationGuards:
    """A GM must not be able to take over a GM/founder account by editing their email or username."""

    async def test_gm_cannot_edit_another_gm(self, client, gm_token, create_user):
        other_gm = await create_user(email="other-gm@example.com", role=UserRole.GM)

        for payload in ({"email": "hijack@example.com"}, {"username": "hijacked"}, {"bio": "hi"}):
            response = await client.put(f"/users/{other_gm.id}", json=payload, headers=bearer(gm_token))
            assert response.status_code == 403, payload

    async def test_gm_cannot_edit_the_founder(self, client, gm_token, founder):
        response = await client.put(
            f"/users/{founder.id}", json={"email": "hijack@example.com"}, headers=bearer(gm_token)
        )

        assert response.status_code == 403

    async def test_gm_cannot_edit_themselves_through_the_admin_endpoint(self, client, gm_token, gm):
        response = await client.put(f"/users/{gm.id}", json={"bio": "x"}, headers=bearer(gm_token))

        assert response.status_code == 403

    async def test_gm_can_edit_a_player_email(self, client, gm_token, create_user):
        player = await create_user(email="edit-me@example.com")

        response = await client.put(
            f"/users/{player.id}", json={"email": "Edited@Example.com"}, headers=bearer(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["email"] == "edited@example.com"

    async def test_founder_can_edit_a_gm(self, client, founder_token, create_user):
        gm = await create_user(email="founder-edits-gm@example.com", role=UserRole.GM)

        response = await client.put(
            f"/users/{gm.id}", json={"email": "renamed-gm@example.com"}, headers=bearer(founder_token)
        )

        assert response.status_code == 200

    async def test_a_rejected_gm_edit_changes_nothing(self, client, gm_token, create_user, db_session):
        other_gm = await create_user(email="untouched@example.com", role=UserRole.GM)

        await client.put(f"/users/{other_gm.id}", json={"email": "hijack@example.com"}, headers=bearer(gm_token))
        await db_session.refresh(other_gm)

        assert other_gm.email == "untouched@example.com"


@pytest.mark.integration
@pytest.mark.asyncio
class TestPartialUpdateValidation:
    @pytest.mark.parametrize("field", ["username", "email"])
    async def test_null_in_a_required_field_is_422(self, client, player_token, field):
        response = await client.put("/users/me", json={field: None, "bio": "x"}, headers=bearer(player_token))

        assert response.status_code == 422

    async def test_null_role_is_422_for_managers(self, client, founder_token, player):
        response = await client.put(
            f"/users/{player.id}", json={"role": None, "bio": "x"}, headers=bearer(founder_token)
        )

        assert response.status_code == 422

    async def test_null_clears_a_nullable_field(self, client, player_token):
        await client.put("/users/me", json={"bio": "something"}, headers=bearer(player_token))

        response = await client.put("/users/me", json={"bio": None}, headers=bearer(player_token))

        assert response.status_code == 200
        assert response.json()["bio"] is None

    async def test_unknown_fields_are_rejected_for_managers(self, client, gm_token, player):
        response = await client.put(
            f"/users/{player.id}", json={"bio": "x", "password": "new-password-1"}, headers=bearer(gm_token)
        )

        assert response.status_code == 422

    async def test_non_object_body_is_422_not_500(self, client, player_token):
        for body in ([], "text", 5):
            response = await client.put("/users/me", json=body, headers=bearer(player_token))
            assert response.status_code == 422, body

    async def test_overlong_free_text_is_422(self, client, player_token):
        for payload in ({"phone": "1" * 101}, {"discord": "d" * 101}, {"bio": "b" * 5001}):
            response = await client.put("/users/me", json=payload, headers=bearer(player_token))
            assert response.status_code == 422, payload

    async def test_create_user_rejects_overlong_password(self, client, gm_token):
        response = await client.post(
            "/users",
            json={"username": "longpass", "email": "longpass@example.com", "password": "p" * 73},
            headers=bearer(gm_token),
        )

        assert response.status_code == 400

    async def test_create_user_normalizes_email(self, client, gm_token):
        response = await client.post(
            "/users",
            json={"username": "normalized", "email": " Normal@Example.COM", "password": "password123"},
            headers=bearer(gm_token),
        )

        assert response.status_code == 201
        assert response.json()["email"] == "normal@example.com"


@pytest.mark.integration
@pytest.mark.asyncio
class TestDefaultAdminProtection:
    async def test_default_admin_cannot_change_own_email(self, client, create_user, login_as):
        admin = await create_user(username="tuttamus", email=settings.ADMIN_LOGIN)
        token = await login_as(admin)

        response = await client.put("/users/me", json={"email": "elsewhere@example.com"}, headers=bearer(token))

        assert response.status_code == 403

    async def test_gm_cannot_update_default_admin(self, client, gm_token, create_user):
        admin = await create_user(username="tuttamus", email=settings.ADMIN_LOGIN, role=UserRole.FOUND_FATHER)

        response = await client.put(f"/users/{admin.id}", json={"bio": "x"}, headers=bearer(gm_token))

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestMe:
    async def test_me_returns_the_current_user(self, client, player, player_token):
        response = await client.get("/users/me", headers=bearer(player_token))

        assert response.status_code == 200
        assert response.json()["id"] == player.id
        assert "hashed_password" not in response.json()
