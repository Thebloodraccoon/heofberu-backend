from fastapi import status
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient, user):
    response = await async_client.post("/auth/login", json={"email": user.email, "password": user._test_password})
    assert response.status_code == status.HTTP_200_OK

    access_token = response.json().get("access_token") or response.json().get("temp_token")
    assert access_token is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_password", ["wrong123", "123456", "password"])
async def test_login_invalid_password(async_client: AsyncClient, user, wrong_password: str):
    response = await async_client.post("/auth/login", json={"email": user.email, "password": wrong_password})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid email or password" in response.text


@pytest.mark.asyncio
async def test_logout(async_client: AsyncClient, user_token: str, refresh_token: str):
    headers = {"Authorization": f"Bearer {user_token}"}
    cookies = {"refresh_token": refresh_token}

    response = await async_client.post("/auth/logout", headers=headers, cookies=cookies)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_refresh_token(async_client: AsyncClient, refresh_token: str):
    cookies = {"refresh_token": refresh_token}
    response = await async_client.post("/auth/refresh", cookies=cookies)

    assert response.status_code == status.HTTP_200_OK
    tokens = response.json()
    assert "access_token" in tokens


@pytest.mark.asyncio
async def test_logout_clears_cookie(async_client: AsyncClient, user_token: str, refresh_token: str):
    headers = {"Authorization": f"Bearer {user_token}"}
    cookies = {"refresh_token": refresh_token}
    response = await async_client.post("/auth/logout", headers=headers, cookies=cookies)

    assert response.status_code == status.HTTP_200_OK

    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    assert 'refresh_token=""' in set_cookie or "Max-Age=0" in set_cookie


@pytest.mark.asyncio
async def test_refresh_token_missing_cookie(async_client: AsyncClient):
    response = await async_client.post("/auth/refresh")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Could not validate credentials" in response.text


@pytest.mark.asyncio
async def test_refresh_token_invalid_format(async_client: AsyncClient):
    cookies = {"refresh_token": "invalid.token.string"}
    response = await async_client.post("/auth/refresh", cookies=cookies)
    assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY]
    assert "Invalid token" in response.text or "Could not validate credentials" in response.text


@pytest.mark.asyncio
async def test_login_requires_twofa(async_client: AsyncClient, user_with_2fa):
    response = await async_client.post(
        "/auth/login",
        json={
            "email": user_with_2fa.email,
            "password": user_with_2fa._test_password,
        },
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "temp_token" in data
    assert "otp_uri" in data
