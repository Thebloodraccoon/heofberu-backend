"""Race CRUD service including ability-bonus and skill management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cached_service import CachedService
from app.features.features.mixins import SourceFeatureMixin
from app.features.features.nested_service import NestedFeatureService
from app.features.races.repository import RaceRepository
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
)
from app.features.skills.mixins import SkillsManagerMixin
from app.models.race_model import Race


class RaceService(
    SkillsManagerMixin,
    SourceFeatureMixin,
    CachedService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceGetAllResponse],
):
    """
    Race-specific CRUD service built on :class:`CachedService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - free-text ``search`` on the race name (via the inherited ``search``
        parameter, pinned by ``RaceRepository``'s ``search_fields``) and
        exact-match ``size`` filtering;
      - management of ability bonuses and granted skills, which live in
        their own association tables and have no generic base-class
        equivalent. ``create_race`` sets them up front, in the same
        transaction as the race itself, via ``BaseService._atomic()``;
      - per-source feature CRUD (``add_feature``/``update_feature``/
        ``remove_feature``) and per-source feature listing
        (``list_features``) inherited from :class:`SourceFeatureMixin`;
      - a delete guard that blocks removing a race still assigned to any
        character (``characters.race_id`` is ``ON DELETE SET NULL`` at the
        DB level, so the guard is what prevents detachment).

    ``get_by_id``, ``get_all``, and ``delete`` are all inherited unchanged
    from ``CachedService``/``BaseService`` — the in-use delete guard lives
    in ``BaseRepository.delete`` (via ``check_in_use_on_delete=True`` +
    ``RaceRepository.is_in_use``). Listing and detail reads are cached via
    ``@use_cache``; the lightweight listing derives its columns from
    ``RaceGetAllResponse``'s field names (id, name, size, is_homebrew) and
    is ordered by ``Race.id``.

    The race responses no longer embed their ``features`` — per-source
    features are read through ``list_features`` (cached under the dedicated
    ``nested_features`` namespace). The service therefore invalidates both
    its own namespace and ``nested_features`` on catalog writes (creating
    or deleting a race also creates/deletes its feature rows).
    """

    repository: RaceRepository

    cache_namespaces = ("races", "nested_features")

    _feature_source_type = FeatureSourceType.RACE

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            get_all_schema=RaceGetAllResponse,
        )
        self._features = NestedFeatureService(db)

    async def create_race(self, race_data: RaceCreate, created_by_id: int | None = None) -> RaceResponse:
        """
        Create a race after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew races) and is not part of ``RaceCreate`` itself, since
        it comes from the authenticated user, not client input.

        ``race_data.ability_bonuses`` / ``race_data.granted_skills`` /
        ``race_data.features`` are optional. If supplied, they're set in
        the *same transaction* as the race itself (base fields + bonuses +
        skills + features all commit together, or none do) via
        ``BaseService._atomic()`` — this is what lets a client create a
        fully-formed race in one request instead of one POST plus extra
        PUTs. Nested features are created through
        ``create_features_for_source`` with ``source_type=RACE``.

        Every write inside ``_atomic()`` passes ``commit=False`` —
        including ``repository.create`` itself — per the hazard documented
        on ``_atomic()``/``BaseRepository.create``.
        """

        skills = await self._resolve_skills(race_data.granted_skills)

        payload = race_data.model_dump(exclude={"ability_bonuses", "granted_skills", "features"})
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if race_data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in race_data.ability_bonuses]
                await self.repository.set_ability_bonuses(item, bonuses, commit=False)

            if skills:
                await self.repository.set_skills(item, skills, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.RACE,
                item.id,
                race_data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return await self._get_response(item.id)

    async def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses."""

        race = await self._get_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        await self.repository.set_ability_bonuses(race, bonuses)
        await self._invalidate_cache()

        return await self._get_response(race_id)
