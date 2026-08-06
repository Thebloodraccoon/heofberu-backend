"""Character feature service: recording, updating, and removing features."""

from sqlalchemy.orm import Session

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.features.exceptions import (
    CharacterFeatureAlreadyKnownException,
    CharacterFeatureNotFoundException,
)
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.features.schemas import (
    CharacterFeatureAdd,
    CharacterFeatureResponse,
    CharacterFeatureUpdate,
)
from app.features.features.exceptions import FeatureNotFoundException
from app.features.features.repository import FeatureRepository
from app.features.users.schemas import UserResponse
from app.models.character_feature_model import CharacterFeature


class CharacterFeatureService(CharacterSubDomainService):
    """
    Record/update/remove reference features on a character.

    Each row in ``character_features`` links a character to a reference
    ``Feature`` and holds optional per-character notes. Uses three
    collaborators:

      - the inherited ``CharacterSubDomainService`` — access control
        only (fetching the owning character to check GM/owner permission
        via ``get_character_for_user``); no feature data lives there.
      - ``CharacterFeatureRepository`` — the ``character_features``
        grant rows (CRUD).
      - ``FeatureRepository`` — looking up the reference feature being
        recorded, so grants always point at an existing feature.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.feature_grant_repository = CharacterFeatureRepository(db)
        self.feature_repository = FeatureRepository(db)

    def get_features(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatureResponse]:
        """List every feature recorded on a character."""

        self.get_character_for_user(character_id, current_user)

        grants = self.feature_grant_repository.get_character_features(character_id)
        return [CharacterFeatureResponse.model_validate(grant) for grant in grants]

    def add_feature(
        self, character_id: int, data: CharacterFeatureAdd, current_user: UserResponse
    ) -> CharacterFeatureResponse:
        """Record a reference feature on a character, with optional notes."""

        self.get_character_for_user(character_id, current_user)

        if not self.feature_repository.exists_by_id(data.feature_id):
            raise FeatureNotFoundException(feature_id=data.feature_id)

        existing = self.feature_grant_repository.get_character_feature_by_feature_id(character_id, data.feature_id)
        if existing:
            raise CharacterFeatureAlreadyKnownException(character_id=character_id, feature_id=data.feature_id)

        grant = self.feature_grant_repository.add_character_feature(character_id, data.feature_id, data.notes)
        return CharacterFeatureResponse.model_validate(grant)

    def update_feature(
        self,
        character_id: int,
        character_feature_id: int,
        data: CharacterFeatureUpdate,
        current_user: UserResponse,
    ) -> CharacterFeatureResponse:
        """Replace the notes on an already-recorded feature."""

        self.get_character_for_user(character_id, current_user)

        grant = self._get_grant_or_404(character_id, character_feature_id)
        updated_grant = self.feature_grant_repository.update_notes(grant, data.notes or "")
        return CharacterFeatureResponse.model_validate(updated_grant)

    def remove_feature(self, character_id: int, character_feature_id: int, current_user: UserResponse) -> bool:
        """Remove a feature grant from a character."""

        self.get_character_for_user(character_id, current_user)

        grant = self._get_grant_or_404(character_id, character_feature_id)
        return self.feature_grant_repository.remove_character_feature(grant)

    def _get_grant_or_404(self, character_id: int, character_feature_id: int) -> CharacterFeature:
        """Fetch a feature grant scoped to the character, or raise ``CharacterFeatureNotFoundException``."""

        grant = self.feature_grant_repository.get_character_feature_by_id(character_id, character_feature_id)
        if not grant:
            raise CharacterFeatureNotFoundException(
                character_id=character_id, character_feature_id=character_feature_id
            )
        return grant
