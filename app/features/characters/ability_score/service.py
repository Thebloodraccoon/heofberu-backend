"""Cache invalidation policy and persistence for effective ability scores."""

from sqlalchemy.orm import Session

from app.features.characters.ability_score.calculator import CharacterAbilityScoreCalculator
from app.features.characters.ability_score.repository import CharacterAbilityScoreCacheRepository
from app.models import CharacterAbilityScore
from app.models.character_model import Character


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

    Entry points:
      - ``compute`` — recompute a character's effective scores from the
        current source rows WITHOUT persisting (read-only use, e.g. the
        feat-prerequisite check in ``CharacterFeatService``, or the
        progression service's ASI cap / hit-point modifier checks).
      - ``refresh`` — ``compute`` + persist. Used by every write path
        that's already known to affect ability scores (feat
        grant/update/remove; character create; race change; level-up
        ASI, via ``CharacterProgressionService``).
      - ``get_or_stale`` — read the existing cache row without
        recomputing. Used by list views that intentionally trade
        freshness for avoiding N recalculations per page.
      - ``get_many_or_stale`` — same as ``get_or_stale`` but for a whole
        listing page in one query (kills the N+1 in
        ``CharacterService.get_characters``).
      - ``for_response`` — thin dispatcher used by
        ``CharacterService._to_response``: ``refresh`` when ``refresh``
        is ``True``, else ``get_or_stale``.
    """

    def __init__(self, db: Session):
        self.calculator = CharacterAbilityScoreCalculator()
        self.cache_repository = CharacterAbilityScoreCacheRepository(db)

    def compute(self, character: Character) -> dict[str, int]:
        """
        Recompute a character's effective ability scores WITHOUT writing
        to the cache table.

        Loads the source bonus rows (race bonuses + feat ASI choices)
        and feeds them to the pure :class:`CharacterAbilityScoreCalculator`.
        Used by read-only callers that need "what would the current
        scores be" — e.g. the feat prerequisite check, which must be
        based on fresh data even if the cache is stale.
        """

        race_bonuses = self.cache_repository.get_race_bonuses(character.race_id)
        feat_increases = self.cache_repository.get_feat_increases(character.id)
        return self.calculator.compute(character, race_bonuses, feat_increases)

    def refresh(self, character: Character) -> CharacterAbilityScore:
        """Recompute effective ability scores for ``character`` and persist them."""

        totals = self.compute(character)
        return self.cache_repository.upsert(character.id, totals)

    def get_or_stale(self, character_id: int) -> CharacterAbilityScore | None:
        """
        Return the existing cache row as-is, without recomputing.
        ``None`` if the character has never had its scores computed
        (e.g. never fetched individually via ``GET /{character_id}``).
        """

        return self.cache_repository.get_by_character_id(character_id)

    def get_many_or_stale(self, character_ids: list[int]) -> dict[int, CharacterAbilityScore]:
        """
        Return the existing cache rows for many characters in one query,
        keyed by ``character_id``. Characters without a row are simply
        absent from the result — see :meth:`get_or_stale`.
        """

        return self.cache_repository.get_many_by_character_ids(character_ids)

    def for_response(self, character: Character, *, refresh: bool = False) -> CharacterAbilityScore | None:
        """
        Return the cache row for serializing a character response:
        freshly recomputed+persisted when ``refresh`` is ``True``,
        otherwise the existing row as-is (or ``None``).
        """

        if refresh:
            return self.refresh(character)
        return self.get_or_stale(character.id)
