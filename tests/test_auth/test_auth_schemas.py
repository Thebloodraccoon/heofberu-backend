from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    TwoFASetupResponse,
    TwoFARequiredResponse,
    TwoFAVerifyRequest,
    LogoutResponse,
    RefreshResponse,
)


def test_login_request_schema():
    schema = LoginRequest(email="user@example.com", password="StrongPass123")
    assert schema.email == "user@example.com"
    assert schema.password == "StrongPass123"


def test_login_response_schema():
    schema = LoginResponse(access_token="abc.def.ghi")
    assert schema.access_token == "abc.def.ghi"


def test_twofa_setup_response_schema():
    schema = TwoFASetupResponse(otp_uri="otpauth://...", temp_token="tmp123")
    assert schema.otp_uri.startswith("otpauth://")
    assert schema.temp_token == "tmp123"


def test_twofa_required_response_schema():
    schema = TwoFARequiredResponse(temp_token="tmp456")
    assert schema.temp_token == "tmp456"


def test_twofa_verify_request_schema():
    schema = TwoFAVerifyRequest(otp_code="123456", temp_token="tmp789")
    assert schema.otp_code == "123456"
    assert schema.temp_token == "tmp789"


def test_logout_response_schema():
    schema = LogoutResponse(detail="Logout successful")
    assert schema.detail == "Logout successful"


def test_refresh_response_schema():
    schema = RefreshResponse(access_token="new.jwt.token")
    assert schema.access_token == "new.jwt.token"
