"""Character feat repository: feat-grant row CRUD."""

from sqlalchemy.orm import Session

from app.constants import CharacterFeatSource
from app.core.base_repository import BaseRepository
from app.models.character_association_models import CharacterFeat


class CharacterFeatRepository(BaseRepository[CharacterFeat]):
    """
    Repository for a character's granted feats (``character_feats``).

    Split out of ``CharacterRepository`` — feat grants are their own
    association table, unrelated to the ``Character`` row's own columns.
    """

    def __init__(self, db: Session):
        super().__init__(CharacterFeat, db)

    def get_character_feats(self, character_id: int) -> list[CharacterFeat]:
        """Get every feat grant for a character."""

        return self.db.query(CharacterFeat).filter(CharacterFeat.character_id == character_id).all()

    def get_character_feat_by_id(self, character_id: int, character_feat_id: int) -> CharacterFeat | None:
        """Fetch a single feat grant by its own id, scoped to the character."""

        return (
            self.db.query(CharacterFeat)
            .filter(
                CharacterFeat.id == character_feat_id,
                CharacterFeat.character_id == character_id,
            )
            .first()
        )

    def get_character_feat_by_feat_id(self, character_id: int, feat_id: int) -> CharacterFeat | None:
        """Fetch a character's grant for a specific feat, if any (used for duplicate checks)."""

        return (
            self.db.query(CharacterFeat)
            .filter(
                CharacterFeat.character_id == character_id,
                CharacterFeat.feat_id == feat_id,
            )
            .first()
        )

    def add_character_feat(
        self,
        character_id: int,
        feat_id: int,
        ability_score_increase_id: int | None,
        *,
        source_type: CharacterFeatSource | str = CharacterFeatSource.GM,
        commit: bool = True,
    ) -> CharacterFeat:
        """
        Grant a feat to a character, with an optional ASI choice.

        ``source_type`` records where the grant came from (default ``GM`` —
        the manual feats endpoint; the level-up endpoint passes ``ASI``).
        ``commit=False`` defers the commit so callers that wrap the grant in
        a transaction (``CharacterProgressionService._atomic``) can commit
        it together with the rest of the level-up.
        """

        grant = CharacterFeat(
            character_id=character_id,
            feat_id=feat_id,
            ability_score_increase_id=ability_score_increase_id,
            source_type=source_type,
        )
        self.db.add(grant)
        if commit:
            self.db.commit()
            self.db.refresh(grant)
        else:
            self.db.flush()
        return grant

    def set_character_feat_ability_score_increase(
        self, grant: CharacterFeat, ability_score_increase_id: int | None
    ) -> CharacterFeat:
        """Set (or clear, if ``None``) the ASI choice on an existing feat grant."""

        grant.ability_score_increase_id = ability_score_increase_id
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def remove_character_feat(self, grant: CharacterFeat) -> bool:
        """Revoke a feat grant."""

        self.db.delete(grant)
        self.db.commit()
        return True
