from fastapi import APIRouter, Depends
from app.core.dependencies import require_keeper_or_founder, RegistrationServiceDep
from app.registration.schemas import RegistrationRequest, RegistrationResponse, RegistrationsResponse

router = APIRouter()


@router.post("/", response_model=dict)
async def submit_application(
    data: RegistrationRequest,
    service: RegistrationServiceDep,
):
    reg = await service.submit_application(data.model_dump())
    return {"registration_id": reg.registration_id}


@router.post("/submit", dependencies=[Depends(require_keeper_or_founder)])
async def approve_application(
    registration_id: str,
    service: RegistrationServiceDep,
):
    await service.approve_application(registration_id)
    return {"detail": "Approved"}

@router.delete("/{registration_id}", response_model=dict)
async def reject_registration(
    registration_id: str,
    registration_service: RegistrationServiceDep,
):
    await registration_service.reject_application(registration_id)
    return {"detail": "Registration rejected successfully."}


@router.get("/", response_model=RegistrationsResponse, dependencies=[Depends(require_keeper_or_founder)])
async def list_applications(
    service: RegistrationServiceDep,
    skip: int = 0,
    limit: int = 50,
):
    items = await service.list_applications(skip, limit)
    return RegistrationsResponse(
        total=len(items),
        items=[RegistrationResponse(**item) for item in items]
    )


@router.get(
    "/{registration_id}",
    response_model=RegistrationResponse,
    dependencies=[Depends(require_keeper_or_founder)],
)
async def get_application_by_id(
    registration_id: str,
    service: RegistrationServiceDep,
) -> RegistrationResponse:
    return await service.get_application_by_id(registration_id)
