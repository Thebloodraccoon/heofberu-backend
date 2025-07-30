import pytest
from app.registration.services import RegistrationService
from app.exceptions.registration_exceptions import RegistrationAlreadyExistsException


@pytest.mark.asyncio
async def test_submit_application_success(mock_repo, user_service, registration_data):
    service = RegistrationService(mock_repo, user_service)
    response = await service.submit_application(registration_data)
    assert response.email == registration_data.email


@pytest.mark.asyncio
async def test_submit_application_duplicate_email(mock_repo, user_service, registration_data):
    mock_repo.redis.exists.return_value = 1
    service = RegistrationService(mock_repo, user_service)
    with pytest.raises(RegistrationAlreadyExistsException):
        await service.submit_application(registration_data)