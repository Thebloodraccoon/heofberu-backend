"""Subrace CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.core.exceptions import RecordNotFoundError
from app.features.features.crud.service import FeatureCrudService
from app.features.races.crud.repository import RaceRepository
from app.features.subraces.ability_bonuses.service import SubraceAbilityBonusService
from app.features.subraces.cache import SUBRACE_CACHE_NAMESPACES, invalidate_subrace_cache
from app.features.subraces.crud.repository import SubraceRepository
from app.features.subraces.crud.schemas import (
    SubraceBriefResponse,
    SubraceCreate,
    SubraceFullResponse,
    SubraceResponse,
    SubraceUpdate,
)
from app.models.subrace_model import Subrace


class SubraceCrudService(
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
      - ``get_by_id`` overridden to return the full picture
        (``SubraceFullResponse``): base fields, ability bonuses, and its
        own SUBRACE-source ``features``;
      - atomic creation of the subrace row alongside its nested ability
        bonuses and SUBRACE-source features, seeded through the dedicated
        capability services (``_ability_bonuses``/``_features``) in the
        same ``_atomic()`` transaction.

    Per-subrace feature writes and ability-bonus replacement live in the
    ``features/`` and ``ability_bonuses/`` subpackages.

    Writes purge the ``races``, ``subrace_features`` and ``features`` cache
    namespaces via :func:`invalidate_subrace_cache` — a superset of what
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
        self._features = FeatureCrudService(db)
        self._ability_bonuses = SubraceAbilityBonusService(db)
        self._race_repository = RaceRepository(db)

    async def list_for_race(self, race_id: int) -> list[SubraceBriefResponse]:
        """Return every subrace belonging to ``race_id``, without their ability bonuses."""

        await self._ensure_race_exists(race_id)
        return [
            SubraceBriefResponse.model_validate(subrace) for subrace in await self.repository.list_for_race(race_id)
        ]

    @use_cache(key_builder=lambda self, item_id: f"{cache_prefix()}:races:subrace:get_by_id:{item_id}")
    async def get_by_id(self, item_id: int) -> SubraceFullResponse:
        """
        Return a subrace with its own SUBRACE-source ``features`` and
        ability bonuses included — overrides ``BaseService.get_by_id``
        (bare ``SubraceResponse``) the same way
        ``ClassCrudService.get_by_id`` overrides its base to return the
        full picture.

        Cached under the ``races`` namespace — every write in this
        subdomain purges it via :func:`invalidate_subrace_cache`, so a
        feature or ability-bonus write on this subrace invalidates this
        cached read too.
        """

        subrace = await self._get_or_404(item_id)
        features = await self._features.list_for_source(FeatureSourceType.SUBRACE, item_id)

        return SubraceFullResponse.model_validate(
            {**SubraceResponse.model_validate(subrace).model_dump(), "features": features}
        )

    async def create_subrace(self, data: SubraceCreate) -> SubraceResponse:
        """
        Create a subrace under ``race_id``.

        Optional nested ``ability_bonuses`` and ``features`` are written in
        the same transaction as the subrace itself (subrace features use
        ``source_type=SUBRACE``).
        """

        await self._ensure_race_exists(data.race_id)
        payload = data.model_dump(exclude={"ability_bonuses", "features"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in data.ability_bonuses]
                await self._ability_bonuses.set_ability_bonuses_for_subrace(item, bonuses, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.SUBRACE,
                item.id,
                data.features,
                commit=False,
            )

        await invalidate_subrace_cache()

        return SubraceResponse.model_validate(await self._get_or_404(item.id))

    async def _ensure_race_exists(self, race_id: int) -> None:
        """
        Raise ``RecordNotFoundError`` when no race with ``race_id`` exists.

        Used by operations that don't target an existing subrace row yet
        (create/list) so a missing race 404s exactly as it did before the
        subdomain split.
        """

        if not await self._race_repository.exists_by_id(race_id):
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))
