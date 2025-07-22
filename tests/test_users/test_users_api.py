from aiosmtplib import status
from httpx import AsyncClient
import pytest

@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient, test_user, test_admin_token):
    response = await client.get(f"/api/users/{test_user.id}", headers={"Authorization": f"Bearer {test_admin_token.credentials}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == test_user.email


@pytest.mark.asyncio
async def test_update_user(client: AsyncClient, test_user, test_admin_token):
    response = await client.patch(
        f"/api/users/{test_user.id}",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
        json={"username": "newname"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == "newname"


@pytest.mark.asyncio
async def test_delete_user(client: AsyncClient, test_user, test_admin_token):
    response = await client.delete(
        f"/api/users/{test_user.id}",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "User deleted"


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient, test_admin_token):
    response = await client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
        json={
            "username": "newuser",
            "email": "new@user.com",
            "password": "password123",
            "role": "player"
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["email"] == "new@user.com"
