from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.constants import UserRole
from app.core.exceptions import GmAccessException
from app.features.auth.service import AuthService
from app.features.auth.token_utils import verify_token
from app.features.characters.attacks.service import CharacterAttackService
from app.features.characters.core.service import CharacterService
from app.features.characters.proficiencies.service import CharacterProficiencyService
from app.features.characters.rolls.service import CharacterRollService
from app.features.characters.spells.service import CharacterSpellService
from app.features.classes.service import ClassService
from app.features.races.service import RaceService
from app.features.skills.service import SkillService
from app.features.spells.service import SpellService
from app.features.users.schemas import UserResponse
from app.features.users.service import UserService
from app.settings import settings

DatabaseDep = Annotated[Session, Depends(settings.get_db)]


def get_user_service(db: DatabaseDep) -> UserService:
    """Get User service instance."""

    return UserService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_auth_service(db: DatabaseDep) -> AuthService:
    """Get Auth service instance."""

    return AuthService(db)


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


CurrentUserDep = Annotated[UserResponse, Depends(get_current_user)]


def require_gm(current_user: CurrentUserDep) -> UserResponse:
    """Require the current user to have the GM (game master) role."""

    if current_user.role != UserRole.GM:
        raise GmAccessException()

    return current_user


GmUserDep = Annotated[UserResponse, Depends(require_gm)]


def get_race_service(db: DatabaseDep) -> RaceService:
    """Get Race service instance."""

    return RaceService(db)


RaceServiceDep = Annotated[RaceService, Depends(get_race_service)]


def get_spell_service(db: DatabaseDep) -> SpellService:
    """Get Spell service instance."""

    return SpellService(db)


SpellServiceDep = Annotated[SpellService, Depends(get_spell_service)]


def get_character_service(db: DatabaseDep) -> CharacterService:
    """Get Character service instance."""

    return CharacterService(db)


CharacterServiceDep = Annotated[CharacterService, Depends(get_character_service)]


def get_character_proficiency_service(db: DatabaseDep) -> CharacterProficiencyService:
    """Get Character proficiency service instance."""

    return CharacterProficiencyService(db)


CharacterProficiencyServiceDep = Annotated[CharacterProficiencyService, Depends(get_character_proficiency_service)]


def get_character_spell_service(db: DatabaseDep) -> CharacterSpellService:
    """Get Character spell service instance."""

    return CharacterSpellService(db)


CharacterSpellServiceDep = Annotated[CharacterSpellService, Depends(get_character_spell_service)]


def get_character_attack_service(db: DatabaseDep) -> CharacterAttackService:
    """Get Character attack service instance."""

    return CharacterAttackService(db)


CharacterAttackServiceDep = Annotated[CharacterAttackService, Depends(get_character_attack_service)]


def get_character_roll_service(db: DatabaseDep) -> CharacterRollService:
    """Get Character roll service instance."""

    return CharacterRollService(db)


CharacterRollServiceDep = Annotated[CharacterRollService, Depends(get_character_roll_service)]


def get_skill_service(db: DatabaseDep) -> SkillService:
    """Get Skill service instance."""

    return SkillService(db)


SkillServiceDep = Annotated[SkillService, Depends(get_skill_service)]


def get_class_service(db: DatabaseDep) -> ClassService:
    """Get Class service instance."""

    return ClassService(db)


ClassServiceDep = Annotated[ClassService, Depends(get_class_service)]
