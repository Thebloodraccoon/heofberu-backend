import pytest
from unittest.mock import AsyncMock, patch
from fastapi import status

from app.registration.schemas import RegistrationRequest


@pytest.fixture
def mock_registration_repo():
    repo = AsyncMock()
    repo.redis.exists = AsyncMock(return_value=0)
    repo.save_application = AsyncMock()
    repo.get_application = AsyncMock()
    repo.list_applications = AsyncMock()
    repo.delete_application = AsyncMock()
    return repo


@pytest.fixture
def mock_send_email():
    with patch("app.emails.sender.send_email_async", new_callable=AsyncMock) as mock_send:
        yield mock_send


@pytest.fixture
def registration_service(mock_registration_repo):
    from app.registration.services import RegistrationService
    from app.users.services import UserService
    from unittest.mock import MagicMock

    # Создаем мок UserService с нужными методами
    user_service = MagicMock()
    user_service.check_username_exists.return_value = None
    user_service.check_email_exists.return_value = None
    user_service.create_user.return_value = None

    service = RegistrationService(mock_registration_repo, user_service)
    return service


@pytest.mark.asyncio
async def test_submit_application_success(
    async_client, registration_service, mock_send_email, test_admin_token
):
    data = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "strongpassword123",
        "role": "player",
    }

    # Мокаем save и get
    registration_service.repo.save_application = AsyncMock()
    registration_service.repo.get_application = AsyncMock(return_value=data)

    with patch("app.core.dependencies.RegistrationServiceDep", lambda: registration_service):
        response = await async_client.post("/registration/", json=data)

    assert response.status_code == status.HTTP_200_OK or status.HTTP_201_CREATED
    assert response.json()["email"] == data["email"]
    assert "password" not in response.json()
