"""Character feature repository: character-feature grant row CRUD."""

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models.character_feature_model import CharacterFeature


class CharacterFeatureRepository(BaseRepository[CharacterFeature]):
    """
    Repository for the features recorded on a character
    (``character_features``).

    Split out of ``CharacterRepository`` — feature grants are their own
    association table, unrelated to the ``Character`` row's own columns.
    """

    def __init__(self, db: Session):
        super().__init__(
            CharacterFeature,
            db,
            default_load_options=[selectinload(CharacterFeature.feature)],
        )

    def get_character_features(self, character_id: int) -> list[CharacterFeature]:
        """Get every feature grant for a character."""

        return (
            self.db.query(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .filter(CharacterFeature.character_id == character_id)
            .all()
        )

    def get_character_feature_by_id(self, character_id: int, character_feature_id: int) -> CharacterFeature | None:
        """Fetch a single feature grant by its own id, scoped to the character."""

        return (
            self.db.query(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .filter(
                CharacterFeature.id == character_feature_id,
                CharacterFeature.character_id == character_id,
            )
            .first()
        )

    def get_character_feature_by_feature_id(self, character_id: int, feature_id: int) -> CharacterFeature | None:
        """Fetch a character's grant for a specific reference feature, if any (used for duplicate checks)."""

        return (
            self.db.query(CharacterFeature)
            .filter(
                CharacterFeature.character_id == character_id,
                CharacterFeature.feature_id == feature_id,
            )
            .first()
        )

    def add_character_feature(self, character_id: int, feature_id: int, notes: str) -> CharacterFeature:
        """Record a reference feature on a character, with per-character notes."""

        grant = CharacterFeature(
            character_id=character_id,
            feature_id=feature_id,
            notes=notes,
        )
        self.db.add(grant)
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def update_notes(self, grant: CharacterFeature, notes: str) -> CharacterFeature:
        """Replace the notes on an existing feature grant."""

        grant.notes = notes
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def remove_character_feature(self, grant: CharacterFeature) -> bool:
        """Remove a feature grant from a character."""

        self.db.delete(grant)
        self.db.commit()
        return True
