import re

from pydantic import BaseModel, field_validator

from app.exceptions.user_exceptions import InvalidEmailException


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, email):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email


class LoginResponse(BaseModel):
    access_token: str


class LogoutResponse(BaseModel):
    detail: str


class RefreshResponse(BaseModel):
    access_token: str
