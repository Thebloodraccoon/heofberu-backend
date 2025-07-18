from fastapi import APIRouter

from app.core.dependencies import AdminUserDep, RegistrationServiceDep
from app.registration.schemas import (
    ApproveResponse,
    RegistrationRequest,
    RegistrationResponse,
    RegistrationsResponse,
    RejectResponse,
)

router = APIRouter()


@router.post("/", response_model=RegistrationResponse)
async def submit_application(
    data: RegistrationRequest,
    service: RegistrationServiceDep,
):
    return await service.submit_application(data)


@router.post("/submit", response_model=ApproveResponse)
async def approve_application(
    registration_id: str,
    service: RegistrationServiceDep,
    _: AdminUserDep,
):
    return await service.approve_application(registration_id)


@router.delete("/{registration_id}", response_model=RejectResponse)
async def reject_registration(
    registration_id: str,
    registration_service: RegistrationServiceDep,
    _: AdminUserDep,
):
    return await registration_service.reject_application(registration_id)


@router.get("/", response_model=RegistrationsResponse)
async def list_applications(
    service: RegistrationServiceDep,
    _: AdminUserDep,
    skip: int = 0,
    limit: int = 50,
):
    return await service.list_applications(skip, limit)


@router.get(
    "/{registration_id}",
    response_model=RegistrationResponse,
)
async def get_application_by_id(
    registration_id: str,
    service: RegistrationServiceDep,
    _: AdminUserDep,
) -> RegistrationResponse:
    return await service.get_application_by_id(registration_id)
