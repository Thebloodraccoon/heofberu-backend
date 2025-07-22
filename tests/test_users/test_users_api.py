from fastapi import status
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_get_users(async_client: AsyncClient, test_admin_token):
    response = await async_client.get("/users/", headers={"Authorization": f"Bearer {test_admin_token.credentials}"})
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_user(async_client: AsyncClient, test_admin_token):
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "securepassword123",
        "role": "player",
    }

    response = await async_client.post(
        "/users/",
        json=payload,
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["username"] == payload["username"]
    assert response.json()["email"] == payload["email"]


@pytest.mark.asyncio
async def test_get_user_by_id(async_client: AsyncClient, test_user, test_admin_token):
    response = await async_client.get(
        f"/users/{test_user.id}",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == test_user.id
    assert response.json()["email"] == test_user.email


@pytest.mark.asyncio
async def test_update_user(async_client: AsyncClient, test_user, test_admin_token):
    payload = {"username": "updatedusername"}

    response = await async_client.put(
        f"/users/{test_user.id}",
        json=payload,
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == payload["username"]


@pytest.mark.asyncio
async def test_delete_user(async_client: AsyncClient, test_user, test_admin_token):
    response = await async_client.delete(
        f"/users/{test_user.id}",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.text == ""