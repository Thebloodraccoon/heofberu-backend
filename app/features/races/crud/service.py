"""Race CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.cached_service import CachedService
from app.features.features.crud.service import FeatureCrudService
from app.features.races.ability_bonuses.service import RaceAbilityBonusService
from app.features.races.cache import RACE_CACHE_NAMESPACES, invalidate_race_cache
from app.features.races.crud.repository import RaceRepository
from app.features.races.schemas import (
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
)
from app.features.races.skills.service import RaceSkillService
from app.models.race_model import Race


class RaceCrudService(
    CachedService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceGetAllResponse],
):
    """
    Race catalog CRUD built on :class:`CachedService`.

    The capability services are composed explicitly in ``__init__`` (no
    mixin MRO):
      - ``create_race`` seeds ability bonuses, granted skills, and nested
        RACE-source features through the dedicated capability services in
        the same ``_atomic()`` transaction.

    Subrace management — full subrace CRUD, per-subrace ability bonuses,
    and per-subrace features (``source_type=SUBRACE``) — lives in the
    self-contained ``app.features.races.subraces`` subdomain, which is
    mounted on the ``/races`` router with its own per-capability service
    dependencies.

    ``get_by_id``, ``get_all``, and ``delete`` are all inherited unchanged
    from ``CachedService``/``BaseService`` — the in-use delete guard lives
    in ``BaseRepository.delete`` (via ``check_in_use_on_delete=True`` +
    ``RaceRepository.is_in_use``).

    The race responses embed their ``subraces`` and their RACE-source
    ``features`` (eager-loaded via ``RaceRepository.default_load_options``);
    ``cache_namespaces`` covers the namespaces any race read hits, and the
    capability services use :func:`invalidate_race_cache` explicitly for
    their own writes.
    """

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            get_all_schema=RaceGetAllResponse,
        )
        self._skills = RaceSkillService(db)
        self._ability_bonuses = RaceAbilityBonusService(db)
        self._features = FeatureCrudService(db)

    async def create_race(self, race_data: RaceCreate) -> RaceResponse:
        """
        Create a race after checking its name isn't already taken.

        ``race_data.ability_bonuses`` / ``race_data.granted_skills`` /
        ``race_data.features`` are optional. If supplied, they're set in the
        *same transaction* as the race itself (base fields + bonuses +
        skills + features all commit together, or none do) via
        ``BaseService._atomic()`` — this is what lets a client create a
        fully-formed race in one request instead of one POST plus extra PUTs.
        Nested features are created through ``create_features_for_source``
        with ``source_type=RACE``.

        Every write inside ``_atomic()`` passes ``commit=False`` —
        including ``repository.create`` itself — per the hazard documented
        on ``_atomic()``/``BaseRepository.create``.
        """

        skills = await self._skills.resolve_skills(race_data.granted_skills)

        payload = race_data.model_dump(exclude={"ability_bonuses", "granted_skills", "features"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if race_data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in race_data.ability_bonuses]
                await self._ability_bonuses.set_ability_bonuses_for_race(item, bonuses, commit=False)

            if skills:
                await self._skills.set_skills_for_race(item, skills, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.RACE,
                item.id,
                race_data.features,
                commit=False,
            )

        await invalidate_race_cache()

        return await self._get_response(item.id)
