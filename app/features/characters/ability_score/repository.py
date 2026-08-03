from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models import CharacterAbilityScore


class CharacterAbilityScoreCacheRepository(BaseRepository[CharacterAbilityScore]):
    """
    Repository for the ``character_ability_scores`` cache table.

    Split out of ``CharacterRepository`` — this is a derived/cached
    table (effective ability scores after race/feat bonuses), distinct
    from both the base ``Character`` row and from
    ``CharacterAbilityScoreCalculator`` (which computes the values but
    never persists them itself). See ``CharacterAbilityCacheService``
    for the single point that decides *when* to recompute + persist.
    """

    def __init__(self, db: Session):
        super().__init__(CharacterAbilityScore, db)

    def get_by_character_id(self, character_id: int) -> CharacterAbilityScore | None:
        """Fetch the cached effective-ability-score row, or None if never computed."""

        return self.db.query(CharacterAbilityScore).filter(CharacterAbilityScore.character_id == character_id).first()

    def upsert(self, character_id: int, totals: dict) -> CharacterAbilityScore:
        """
        Create or update the cached effective ability scores for a
        character. ``totals`` keys are ``strength_total``,
        ``dexterity_total``, ``constitution_total``,
        ``intelligence_total``, ``wisdom_total``, ``charisma_total``.
        """

        cache = self.get_by_character_id(character_id)
        if cache is None:
            cache = CharacterAbilityScore(character_id=character_id, **totals)
            self.db.add(cache)
        else:
            for field, value in totals.items():
                setattr(cache, field, value)

        self.db.commit()
        self.db.refresh(cache)
        return cache
