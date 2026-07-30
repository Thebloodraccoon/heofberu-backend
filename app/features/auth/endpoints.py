from fastapi import APIRouter, Request, Response

from app.core.dependencies import AuthServiceDep, CurrentUserDep

from .schemas import LoginRequest, LoginResponse, LogoutResponse, RefreshResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response, auth_service: AuthServiceDep):
    return auth_service.login(request, response)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    auth_service: AuthServiceDep,
    _: CurrentUserDep,
):
    logout_response = auth_service.logout_user()
    response.delete_cookie(key="refresh_token", httponly=True, samesite="none", secure=True)
    return logout_response


@router.post("/refresh", response_model=RefreshResponse)
def refresh_tokens(http_request: Request, auth_service: AuthServiceDep):
    refresh_token = http_request.cookies.get("refresh_token", "")
    return auth_service.refresh_tokens(refresh_token)
