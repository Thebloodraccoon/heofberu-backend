from pydantic import UUID4, BaseModel

from app.users.schemas import UserCreate


class RegistrationRequest(UserCreate):
    pass


class RegistrationResponse(RegistrationRequest):
    registration_id: UUID4


class RegistrationsResponse(BaseModel):
    total: int
    items: list[RegistrationResponse]


class ApproveResponse(BaseModel):
    detail: str


class RejectResponse(BaseModel):
    detail: str
