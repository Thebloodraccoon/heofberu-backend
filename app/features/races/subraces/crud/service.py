"""Subrace CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.exceptions import RecordNotFoundError
from app.features.races.crud.repository import RaceRepository
from app.features.races.subraces.ability_bonuses.service import SubraceAbilityBonusService
from app.features.races.subraces.base import SubraceScopedMixin
from app.features.races.subraces.cache import SUBRACE_CACHE_NAMESPACES, invalidate_subrace_cache
from app.features.races.subraces.crud.repository import SubraceRepository
from app.features.races.subraces.crud.schemas import SubraceCreate, SubraceResponse, SubraceUpdate
from app.features.shared.features.nested_service import NestedFeatureService
from app.models.subrace_model import Subrace


class SubraceCrudService(
    SubraceScopedMixin,
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse, None],
):
    """
    Subrace catalog CRUD built on :class:`BaseService`.

    Extends the generic base with:
      - race-scoped 404s (``SubraceNotFoundException`` instead of the
        base ``RecordNotFoundError``, and belonging to the right
        ``race_id``) via :class:`SubraceScopedMixin`;
      - a race-existence guard for operations that don't target an
        existing subrace row yet (create/list), so a missing race still
        turns into a 404;
      - atomic creation of the subrace row alongside its nested ability
        bonuses and SUBRACE-source features, seeded through the dedicated
        capability services (``_ability_bonuses``/``_features``) in the
        same ``_atomic()`` transaction.

    Per-subrace feature writes and ability-bonus replacement live in the
    ``features/`` and ``ability_bonuses/`` subpackages.

    Writes purge the ``races`` and ``nested_features`` cache namespaces
    via :func:`invalidate_subrace_cache` — the same namespaces
    ``RaceCrudService`` uses, since subrace rows (and their features) are
    embedded in cached race responses.
    """

    repository: SubraceRepository

    cache_namespaces = SUBRACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )
        self._features = NestedFeatureService(db)
        self._ability_bonuses = SubraceAbilityBonusService(db)
        self._race_repository = RaceRepository(db)

    async def list_for_race(self, race_id: int) -> list[SubraceResponse]:
        """Return every subrace belonging to ``race_id``, with their ability bonuses."""

        await self._ensure_race_exists(race_id)
        return [SubraceResponse.model_validate(sr) for sr in await self.repository.list_for_race(race_id)]

    async def get_subrace(self, race_id: int, subrace_id: int) -> SubraceResponse:
        """Return a single subrace (scoped to ``race_id``)."""

        return SubraceResponse.model_validate(await self._get_or_404_for_race(race_id, subrace_id))

    async def create_subrace(
        self, race_id: int, data: SubraceCreate, created_by_id: int | None = None
    ) -> SubraceResponse:
        """
        Create a subrace under ``race_id``.

        Optional nested ``ability_bonuses`` and ``features`` are written in
        the same transaction as the subrace itself (subrace features use
        ``source_type=SUBRACE``).
        """

        await self._ensure_race_exists(race_id)

        payload = data.model_dump(exclude={"ability_bonuses", "features"})
        payload["race_id"] = race_id
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in data.ability_bonuses]
                await self._ability_bonuses.set_ability_bonuses_for_subrace(item, bonuses, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.SUBRACE,
                item.id,
                data.features,
                created_by_id,
                commit=False,
            )

        await invalidate_subrace_cache()

        return SubraceResponse.model_validate(await self._get_or_404_for_race(race_id, item.id))

    async def update_subrace(self, race_id: int, subrace_id: int, data: SubraceUpdate) -> SubraceResponse:
        """Apply partial updates to an existing subrace."""

        await self._get_or_404_for_race(race_id, subrace_id)
        return await self.update(subrace_id, data)

    async def delete_subrace(self, race_id: int, subrace_id: int) -> None:
        """Delete a subrace, cascading to its ability bonuses and features."""

        await self._get_or_404_for_race(race_id, subrace_id)
        await self.delete(subrace_id)

    async def _ensure_race_exists(self, race_id: int) -> None:
        """
        Raise ``RecordNotFoundError`` when no race with ``race_id`` exists.

        Used by operations that don't target an existing subrace row yet
        (create/list) so a missing race 404s exactly as it did before the
        subdomain split.
        """

        if not await self._race_repository.exists_by_id(race_id):
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))
