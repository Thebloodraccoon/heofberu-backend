from fastapi import APIRouter, Request, Response

from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LoginResponseUnion,
    LogoutResponse,
    RefreshResponse,
    TwoFAVerifyRequest,
)
from app.core.dependencies import AuthServiceDep, CurrentUserDep

router = APIRouter()


@router.post("/login", response_model=LoginResponseUnion)
def login(request: LoginRequest, response: Response, auth_service: AuthServiceDep):
    return auth_service.login(request, response)


@router.post("/2fa/verify", response_model=LoginResponse)
def verify_2fa(request: TwoFAVerifyRequest, response: Response, auth_service: AuthServiceDep):
    return auth_service.verify_2fa(request, response)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    http_request: Request,
    response: Response,
    auth_service: AuthServiceDep,
    _: CurrentUserDep,
):
    access_token = (http_request.headers.get("Authorization") or "").replace("Bearer ", "")
    refresh_token = http_request.cookies.get("refresh_token", "")
    logout_response = await auth_service.logout_user(access_token, refresh_token)

    response.delete_cookie(key="refresh_token", httponly=True, samesite="none", secure=True)

    return logout_response


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_tokens(http_request: Request, auth_service: AuthServiceDep):
    refresh_token = http_request.cookies.get("refresh_token", "")
    return await auth_service.refresh_tokens(refresh_token)
