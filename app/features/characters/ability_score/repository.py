"""Cache-table repository for a character's effective ability scores."""

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models import CharacterAbilityScore
from app.models.character_association_models import CharacterFeat
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus


class CharacterAbilityScoreCacheRepository(BaseRepository[CharacterAbilityScore]):
    """
    Repository for the ``character_ability_scores`` cache table.

    Split out of ``CharacterRepository`` — this is a derived/cached
    table (effective ability scores after race/feat bonuses), distinct
    from both the base ``Character`` row and from
    ``CharacterAbilityScoreCalculator`` (which computes the values but
    never persists them itself). See ``CharacterAbilityCacheService``
    for the single point that decides *when* to recompute + persist.

    Also owns the source-bonus queries the calculator needs
    (``get_race_bonuses`` / ``get_feat_increases``) — these moved here
    from the old calculator so it could become fully pure (no ``Session``).
    """

    def __init__(self, db: Session):
        super().__init__(CharacterAbilityScore, db)

    def get_by_character_id(self, character_id: int) -> CharacterAbilityScore | None:
        """Fetch the cached effective-ability-score row, or None if never computed."""

        return self.db.query(CharacterAbilityScore).filter(CharacterAbilityScore.character_id == character_id).first()

    def get_many_by_character_ids(self, character_ids: list[int]) -> dict[int, CharacterAbilityScore]:
        """
        Fetch the cache rows for many characters in a single query,
        keyed by ``character_id``. Empty input returns ``{}``.

        This is what lets ``CharacterService.get_characters`` attach
        cached ability scores to a whole listing page in one query
        instead of one ``get_by_character_id`` per row (the old N+1).
        """

        if not character_ids:
            return {}

        rows = self.db.query(CharacterAbilityScore).filter(CharacterAbilityScore.character_id.in_(character_ids)).all()
        return {row.character_id: row for row in rows}

    def get_race_bonuses(self, race_id: int | None) -> list[RaceAbilityBonus]:
        """Fetch a race's ability bonuses, or ``[]`` for a character with no race."""

        if race_id is None:
            return []

        return self.db.query(RaceAbilityBonus).filter(RaceAbilityBonus.race_id == race_id).all()

    def get_feat_increases(self, character_id: int) -> list[FeatAbilityScoreIncrease]:
        """Fetch the ASI choices granted to a character via their feat grants."""

        return (
            self.db.query(FeatAbilityScoreIncrease)
            .join(CharacterFeat, CharacterFeat.ability_score_increase_id == FeatAbilityScoreIncrease.id)
            .filter(CharacterFeat.character_id == character_id)
            .options(selectinload(FeatAbilityScoreIncrease.feat))
            .all()
        )

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
