"""Race CRUD service including ability-bonus, skill, and subrace management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cached_service import CachedService
from app.features.features.mixins import SourceFeatureMixin
from app.features.features.nested_service import NestedFeatureService
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.races.exceptions import SubraceNotFoundException
from app.features.races.repository import RaceRepository
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
    SubraceAbilityBonusesUpdate,
    SubraceCreate,
    SubraceResponse,
    SubraceUpdate,
)
from app.features.skills.mixins import SkillsManagerMixin
from app.models.race_model import Race
from app.models.subrace_model import Subrace


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
      - full subrace CRUD (``create_subrace``/``get_subrace``/
        ``list_subraces``/``update_subrace``/``delete_subrace``),
        per-subrace ability bonuses, and per-subrace features
        (``source_type=SUBRACE``);
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

    The race responses embed their ``subraces`` but not their ``features`` —
    per-source features are read through ``list_features`` (cached under the
    dedicated ``nested_features`` namespace). The service therefore
    invalidates its own namespace plus the nested feature namespace on
    catalog writes (creating or deleting a race also creates/deletes its
    feature and subrace rows).
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

        skills = await self._resolve_skills(race_data.granted_skills)

        payload = race_data.model_dump(
            exclude={"ability_bonuses", "granted_skills", "features"}
        )
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

    async def _get_subrace_or_404(self, race_id: int, subrace_id: int) -> Subrace:
        """Return the subrace or raise a 404 (also when it belongs to another race)."""

        subrace = await self.repository.get_subrace(race_id, subrace_id)
        if subrace is None:
            raise SubraceNotFoundException(race_id, subrace_id)

        return subrace

    async def list_subraces(self, race_id: int) -> list[SubraceResponse]:
        """Return every subrace belonging to ``race_id``."""

        await self._get_or_404(race_id)
        return [SubraceResponse.model_validate(sr) for sr in await self.repository.list_subraces(race_id)]

    async def get_subrace(self, race_id: int, subrace_id: int) -> SubraceResponse:
        """Return a single subrace (scoped to ``race_id``)."""

        return SubraceResponse.model_validate(await self._get_subrace_or_404(race_id, subrace_id))

    async def create_subrace(
        self, race_id: int, data: SubraceCreate, created_by_id: int | None = None
    ) -> SubraceResponse:
        """
        Create a subrace under ``race_id``.

        Optional nested ``ability_bonuses`` and ``features`` are written in
        the same transaction as the subrace itself (subrace features use
        ``source_type=SUBRACE``).
        """

        race = await self._get_or_404(race_id)

        payload = data.model_dump(exclude={"ability_bonuses", "features"})
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create_subrace(race, payload, commit=False)

            if data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in data.ability_bonuses]
                await self.repository.set_subrace_ability_bonuses(item, bonuses, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.SUBRACE,
                item.id,
                data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return SubraceResponse.model_validate(await self._get_subrace_or_404(race_id, item.id))

    async def update_subrace(
        self, race_id: int, subrace_id: int, data: SubraceUpdate
    ) -> SubraceResponse:
        """Apply partial updates to an existing subrace."""

        subrace = await self._get_subrace_or_404(race_id, subrace_id)
        await self.repository.update_subrace(subrace, data.model_dump(exclude_none=True))
        await self._invalidate_cache()

        return SubraceResponse.model_validate(await self._get_subrace_or_404(race_id, subrace_id))

    async def delete_subrace(self, race_id: int, subrace_id: int) -> None:
        """Delete a subrace, cascading to its ability bonuses and features."""

        subrace = await self._get_subrace_or_404(race_id, subrace_id)
        await self.repository.delete_subrace(subrace)
        await self._invalidate_cache()

    async def set_subrace_ability_bonuses(
        self, race_id: int, subrace_id: int, data: SubraceAbilityBonusesUpdate
    ) -> SubraceResponse:
        """Fully replace a subrace's ability score bonuses."""

        subrace = await self._get_subrace_or_404(race_id, subrace_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        await self.repository.set_subrace_ability_bonuses(subrace, bonuses)
        await self._invalidate_cache()

        return SubraceResponse.model_validate(await self._get_subrace_or_404(race_id, subrace_id))

    async def list_subrace_features(self, race_id: int, subrace_id: int) -> list:
        """Return every feature owned by the subrace."""

        await self._get_subrace_or_404(race_id, subrace_id)
        return await self._features.list_for_source(FeatureSourceType.SUBRACE, subrace_id)

    async def add_subrace_feature(
        self, race_id: int, subrace_id: int, data: NestedFeatureCreate, created_by_id: int | None = None
    ) -> NestedFeatureResponse:
        """Add a new feature to the subrace (``source_type=SUBRACE``), atomically."""

        subrace = await self._get_subrace_or_404(race_id, subrace_id)
        return await self._mutate_feature(
            subrace,
            FeatureSourceType.SUBRACE,
            lambda: self._features.create_feature_for_source(
                FeatureSourceType.SUBRACE, subrace.id, data, created_by_id, commit=False
            ),
        )

    async def update_subrace_feature(
        self, race_id: int, subrace_id: int, feature_id: int, update_data: FeatureUpdate
    ) -> NestedFeatureResponse:
        """Update an existing feature owned by the subrace in place."""

        subrace = await self._get_subrace_or_404(race_id, subrace_id)
        fields = update_data.model_dump(exclude_unset=True)
        return await self._mutate_feature(
            subrace,
            FeatureSourceType.SUBRACE,
            lambda: self._features.update_feature_for_source(
                FeatureSourceType.SUBRACE, subrace.id, feature_id, fields, commit=False
            ),
        )

    async def remove_subrace_feature(self, race_id: int, subrace_id: int, feature_id: int) -> None:
        """Delete a feature owned by the subrace, atomically."""

        subrace = await self._get_subrace_or_404(race_id, subrace_id)
        await self._mutate_feature(
            subrace,
            FeatureSourceType.SUBRACE,
            lambda: self._features.delete_feature_for_source(
                FeatureSourceType.SUBRACE, subrace.id, feature_id, commit=False
            ),
        )
