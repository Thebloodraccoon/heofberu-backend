from sqlalchemy.orm import Session

from app.exceptions.character_exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.characters.repository import CharacterRepository
from app.features.characters.schemas import CharacterCreate, CharacterResponse, CharacterUpdate
from app.features.users.schemas import UserResponse


class CharacterService:
    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)

    def get_characters(self, current_user: UserResponse) -> list[CharacterResponse]:
        """GM sees every character. Players see only their own."""
        if current_user.role == "gm":
            characters = self.repository.get_all()
        else:
            characters = self.repository.get_all_by_owner(current_user.id)

        return [CharacterResponse.model_validate(character) for character in characters]

    def get_character(self, character_id: int, current_user: UserResponse) -> CharacterResponse:
        character = self.repository.get_by_id(character_id)
        if not character:
            raise CharacterNotFoundException(character_id=character_id)

        self._check_access(character, current_user)
        return CharacterResponse.model_validate(character)

    def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """Both GM and players can create characters, always owned by themselves."""
        character = self.repository.create(character_data.model_dump(), owner_id=current_user.id)
        return CharacterResponse.model_validate(character)

    def update_character(
        self, character_id: int, update_data: CharacterUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        character = self.repository.get_by_id(character_id)
        if not character:
            raise CharacterNotFoundException(character_id=character_id)

        self._check_access(character, current_user)

        fields = update_data.model_dump(exclude_unset=True)
        updated_character = self.repository.update(character, fields)
        return CharacterResponse.model_validate(updated_character)

    @staticmethod
    def _check_access(character, current_user: UserResponse) -> None:
        """GM can access any character. Players can only access their own."""
        if current_user.role == "gm":
            return

        if character.owner_id != current_user.id:
            raise CharacterAccessDeniedException()
