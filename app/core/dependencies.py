from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.exceptions.auth_exceptions import GmAccessException
from app.features.auth.services import AuthService
from app.features.auth.token_utils import verify_token
from app.features.characters.services import CharacterService
from app.features.races.services import RaceService
from app.features.spells.services import SpellService
from app.features.users.schemas import UserResponse
from app.features.users.services import UserService
from app.settings import settings

DatabaseDep = Annotated[Session, Depends(settings.get_db)]


def get_user_service(db: DatabaseDep) -> UserService:
    """Get User service instance."""
    return UserService(db)


def get_auth_service(db: DatabaseDep) -> AuthService:
    """Get Auth service instance."""
    return AuthService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

security = HTTPBearer(
    scheme_name="JWT Bearer",
    description="JWT Bearer token for authentication",
    auto_error=False,
)
TokenDep = Annotated[HTTPAuthorizationCredentials | None, Depends(security)]


def get_current_user(
    user_service: UserServiceDep,
    token: TokenDep,
) -> UserResponse:
    email = verify_token(token, "access")
    return user_service.get_user_by_email(email)


def require_gm(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Require the current user to have the GM (game master) role."""
    if current_user.role != "gm":
        raise GmAccessException()

    return current_user


def get_race_service(db: DatabaseDep) -> RaceService:
    """Get Race service instance."""
    return RaceService(db)


def get_spell_service(db: DatabaseDep) -> SpellService:
    """Get Spell service instance."""
    return SpellService(db)


def get_character_service(db: DatabaseDep) -> CharacterService:
    """Get Character service instance."""
    return CharacterService(db)


RaceServiceDep = Annotated[RaceService, Depends(get_race_service)]
SpellServiceDep = Annotated[SpellService, Depends(get_spell_service)]
CharacterServiceDep = Annotated[CharacterService, Depends(get_character_service)]

CurrentUserDep = Annotated[UserResponse, Depends(get_current_user)]
GmUserDep = Annotated[UserResponse, Depends(require_gm)]
