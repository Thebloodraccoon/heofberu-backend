"""Cache invalidation policy and persistence for effective ability scores."""

from sqlalchemy.orm import Session

from app.features.characters.ability_score.calculator import CharacterAbilityScoreCalculator
from app.features.characters.ability_score.repository import CharacterAbilityScoreCacheRepository
from app.models import CharacterAbilityScore
from app.models.character_model import Character

# Fields on CharacterUpdate/CharacterCreate that, if changed, invalidate
# the cached effective ability scores and require a recalculation before
# the next response — either because they're a base ability score
# themselves, or because they change which race's bonuses apply.
#
# Lives here (not in core.service) since this is now the single place
# that decides "does this change require a cache refresh" — every
# caller that mutates something ability-affecting should go through
# this service rather than re-deriving its own field set.
ABILITY_AFFECTING_FIELDS = {
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "race_id",
}


class CharacterAbilityCacheService:
    """
    Single point of decision for "when does the effective-ability-score
    cache need recomputing", and the only place that writes to
    ``CharacterAbilityScoreCacheRepository``.

    Before this existed, three call sites each decided independently
    when to recalculate: ``CharacterService._to_response`` (via
    ``_ABILITY_AFFECTING_FIELDS``), ``CharacterFeatService`` (always,
    on every feat write), and race changes (indirectly, via the same
    field set). Consolidating them here means a new ability-affecting
    change (e.g. a future background bonus source) only needs to be
    wired into this one class, not hunted down across every sub-service.

    Two entry points:
      - ``refresh`` — unconditionally recompute + persist. Used by
        every write path that's already known to affect ability scores
        (feat grant/update/remove; character create; any update whose
        fields intersect ``ABILITY_AFFECTING_FIELDS``).
      - ``get_or_stale`` — read the existing cache row without
        recomputing. Used by list views that intentionally trade
        freshness for avoiding N recalculations per page (see
        ``CharacterService.get_characters``).
    """

    def __init__(self, db: Session):
        self.calculator = CharacterAbilityScoreCalculator(db)
        self.cache_repository = CharacterAbilityScoreCacheRepository(db)

    def refresh(self, character: Character) -> CharacterAbilityScore:
        """Recompute effective ability scores for ``character`` and persist them."""

        totals = self.calculator.compute(character)
        return self.cache_repository.upsert(character.id, totals)

    def get_or_stale(self, character_id: int) -> CharacterAbilityScore | None:
        """
        Return the existing cache row as-is, without recomputing.
        ``None`` if the character has never had its scores computed
        (e.g. never fetched individually via ``GET /{character_id}``).
        """

        return self.cache_repository.get_by_character_id(character_id)

    @staticmethod
    def fields_affect_ability_scores(fields: set[str]) -> bool:
        """Return whether any of the given updated field names require a cache refresh."""

        return bool(ABILITY_AFFECTING_FIELDS & fields)
