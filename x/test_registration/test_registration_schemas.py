from app.registration.schemas import RegistrationRequest, RegistrationResponse
import uuid


def test_registration_request_schema():
    data = RegistrationRequest(username="user", email="user@test.com", password="12345678")
    assert data.username == "user"


def test_registration_response_schema():
    reg_id = uuid.uuid4()
    data = RegistrationResponse(
        username="user", email="user@test.com", password="12345678", registration_id=reg_id
    )
    assert data.registration_id == reg_id
