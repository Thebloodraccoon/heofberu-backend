import pytest
from fastapi import status

from app.auth.utils.token_utils import decode_token


def test_login_success(client, user):
    response = client.post("/auth/login", json={"email": user.email, "password": user._test_password})
    assert response.status_code == status.HTTP_200_OK

    access_token = response.json().get("access_token") or response.json().get("temp_token")
    assert access_token is not None


@pytest.mark.parametrize("wrong_password", ["wrong123", "123456", "password"])
def test_login_invalid_password(client, user, wrong_password):
    response = client.post("/auth/login", json={"email": user.email, "password": wrong_password})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid email or password" in response.text


def test_logout(client, user_token, redis_test):
    headers = {"Authorization": f"{user_token.scheme} {user_token.credentials}"}
    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["detail"] == "Successful logout"

    payload = decode_token(user_token.credentials)
    jti = payload["jti"]
    redis_value = redis_test.get(f"blacklist:{jti}")
    assert redis_value is not None


def test_refresh_token(client, test_user, jwt_manager):
    refresh_token = jwt_manager.create_token(
        user_id=test_user.id,
        token_type="refresh",
    )
    response = client.post("/auth/refresh", cookies={"refresh_token": refresh_token})

    assert response.status_code == status.HTTP_200_OK
    tokens = response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens