from fastapi import APIRouter, HTTPException, Depends

from app.registration.schemas import (
    RegistrationRequest,
    RegistrationResponse,
    RegistrationsResponse
)
from app.registration.services import RegistrationService
from app.core.dependencies import (
    get_registration_repository,
    get_user_service,
    require_keeper_or_founder
)
from app.registration.repository import RegistrationRepository
from app.users.services import UserService

router = APIRouter()


@router.post("/", response_model=dict)
async def submit_application(
    data: RegistrationRequest,
    repo: RegistrationRepository = Depends(get_registration_repository),
    user_service: UserService = Depends(get_user_service),
):
    service = RegistrationService(repo, user_service)
    reg_id = await service.submit_application(data.dict())
    return {"registration_id": reg_id}


@router.post("/submit", dependencies=[Depends(require_keeper_or_founder)])
async def approve_application(
    registration_id: str,
    repo: RegistrationRepository = Depends(get_registration_repository),
    user_service: UserService = Depends(get_user_service),
):
    service = RegistrationService(repo, user_service)
    await service.approve_application(registration_id)
    return {"detail": "Approved"}


@router.get("/", response_model=RegistrationsResponse, dependencies=[Depends(require_keeper_or_founder)])
async def list_applications(
    skip: int = 0,
    limit: int = 50,
    repo: RegistrationRepository = Depends(get_registration_repository),
):
    items = await repo.list_applications(skip, limit)
    return RegistrationsResponse(total=len(items), items=items)


@router.get("/{registration_id}", response_model=RegistrationResponse, dependencies=[Depends(require_keeper_or_founder)])
async def get_application(
    registration_id: str,
    repo: RegistrationRepository = Depends(get_registration_repository),
):
    app = await repo.get_application(registration_id)
    if not app:
        raise HTTPException(status_code=404, detail="Not found")
    return RegistrationResponse(**app, registration_id=registration_id)
