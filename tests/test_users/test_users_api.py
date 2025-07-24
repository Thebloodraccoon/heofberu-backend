from fastapi import status
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_get_users(async_client: AsyncClient, test_admin_token):
    response = await async_client.get("/users/", headers={"Authorization": f"Bearer {test_admin_token.credentials}"})
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"username": "newuser1", "email": "newuser1@example.com", "password": "securepassword123", "role": "player"},
        {"username": "keeperuser", "email": "keeper@example.com", "password": "securepassword123", "role": "keeper"},
        {
            "username": "founder",
            "email": "founder@example.com",
            "password": "securepassword123",
            "role": "found_father",
        },
    ],
)
async def test_create_user(async_client: AsyncClient, test_admin_token, payload):
    response = await async_client.post(
        "/users/",
        json=payload,
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["username"] == payload["username"]
    assert response.json()["email"] == payload["email"]
    assert response.json()["role"] == payload["role"]


@pytest.mark.asyncio
@pytest.mark.parametrize("user_fixture", ["test_user"])
async def test_get_user_by_id(async_client: AsyncClient, request, test_admin_token, user_fixture):
    user = request.getfixturevalue(user_fixture)
    response = await async_client.get(
        f"/users/{user.id}",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == user.id
    assert response.json()["email"] == user.email


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update_payload",
    [
        {"username": "updatedusername"},
        {"email": "updatedemail@example.com"},
        {"role": "keeper"},
    ],
)
async def test_update_user(async_client: AsyncClient, test_user, test_admin_token, update_payload):
    response = await async_client.put(
        f"/users/{test_user.id}",
        json=update_payload,
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_200_OK
    for key, value in update_payload.items():
        assert response.json()[key] == value


@pytest.mark.asyncio
@pytest.mark.parametrize("user_fixture", ["test_user"])
async def test_delete_user(async_client: AsyncClient, request, test_admin_token, user_fixture):
    user = request.getfixturevalue(user_fixture)
    response = await async_client.delete(
        f"/users/{user.id}",
        headers={"Authorization": f"Bearer {test_admin_token.credentials}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.text == ""
