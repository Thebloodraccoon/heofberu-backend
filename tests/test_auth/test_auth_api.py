import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_login_success(async_client, test_user):
    response = await async_client.post("/auth/login", json={
        "email": test_user.email,
        "password": "testpassword123",
    })
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data or "temp_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(async_client, test_user):
    response = await async_client.post("/auth/login", json={
        "email": test_user.email,
        "password": "wrongpassword",
    })
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_invalid_email(async_client):
    response = await async_client.post("/auth/login", json={
        "email": "invalid-email",
        "password": "anything",
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_logout_success(async_client, test_user_token):
    response = await async_client.post("/auth/logout", headers={
        "Authorization": f"Bearer {test_user_token.credentials}"
    })
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["detail"] == "Successfully logged out"


@pytest.mark.asyncio
async def test_refresh_success(async_client, test_user_token):
    response = await async_client.post("/auth/refresh", headers={
        "Authorization": f"Bearer {test_user_token.credentials}"
    })
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_refresh_with_blacklisted_token(async_client, redis_test, test_user_token):
    await redis_test.set(test_user_token.credentials, "blacklisted")

    response = await async_client.post("/auth/refresh", headers={
        "Authorization": f"Bearer {test_user_token.credentials}"
    })
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
