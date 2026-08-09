"""Background CRUD service including granted-skill management."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.backgrounds.repository import BackgroundRepository
from app.features.backgrounds.schemas import (
    BackgroundCreate,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
    SkillsUpdate,
)
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.features.schemas import FeaturesReplace
from app.features.features.service import create_features_for_source, replace_features_for_source
from app.models.background_model import Background


class BackgroundService(
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, BackgroundGetAllResponse]
):
    """
    Background-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - management of granted skills, which live in their own association
        table (``background_skills``) and have no generic base-class
        equivalent. ``create_background`` can optionally set them up
        front, in the same transaction as the background itself.

    Unlike ``RaceService``, deletion is *not* blocked by characters
    bearing the background: its FK on ``characters.background_id`` is
    ``ON DELETE SET NULL``, so deleting a background in use simply
    detaches it from any characters. It IS blocked (409) once one of the
    background's features has been granted to a character — those grants
    live in ``character_features`` and must be revoked first, see
    ``BackgroundRepository.is_in_use``.

    ``get_by_id`` and ``get_all`` are inherited unchanged from
    ``BaseService``. The listing falls back to the eager-loaded
    ``repository.get_all`` because ``BackgroundGetAllResponse`` contains
    the ``granted_skills`` relationship, which the base column-select path
    cannot load. Listing and detail reads are cached via ``@use_cache``;
    because a background's writes also touch the ``features`` table
    (BACKGROUND-source rows), the service invalidates both its own
    namespace and ``features``.
    """

    repository: BackgroundRepository

    cache_namespaces = ("backgrounds", "features")

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            get_all_schema=BackgroundGetAllResponse,
        )

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[BackgroundGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return await super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    async def get_by_id(self, item_id: int) -> BackgroundResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return await super().get_by_id(item_id)

    async def create_background(
        self, background_data: BackgroundCreate, created_by_id: int | None = None
    ) -> BackgroundResponse:
        """
        Create a background after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant
        mainly for homebrew backgrounds) and is not part of
        ``BackgroundCreate`` itself, since it comes from the authenticated
        user, not client input.

        ``background_data.granted_skills`` / ``background_data.features``
        are optional. If supplied, they're set in the *same transaction*
        as the background itself — base fields + skills + features commit
        together, or none do. See ``RaceService.create_race`` for the same
        pattern and the reasoning behind every nested write passing
        ``commit=False``. Nested features are created through
        ``create_features_for_source`` with ``source_type=BACKGROUND``.
        """

        skills = (
            await self.resolve_ids(
                self.repository.get_skills_by_ids,
                background_data.granted_skills,
                "Skills",
            )
            if background_data.granted_skills
            else None
        )

        payload = background_data.model_dump(exclude={"granted_skills", "features"})
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if skills:
                await self.repository.set_skills(item, skills, commit=False)

            await create_features_for_source(
                self.repository.db,
                FeatureSourceType.BACKGROUND,
                item.id,
                background_data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return self.response_schema.model_validate(await self._get_or_404(item.id))

    async def set_skills(self, background_id: int, data: SkillsUpdate) -> BackgroundResponse:
        """Fully replace the skills granted by a background."""

        background = await self._get_or_404(background_id)

        skills = await self.resolve_ids(self.repository.get_skills_by_ids, data.skill_ids, "Skills")

        await self.repository.set_skills(background, skills)
        await self._invalidate_cache()
        return self.response_schema.model_validate(await self._get_or_404(background_id))

    async def replace_background_features(
        self, background_id: int, data: FeaturesReplace, created_by_id: int | None = None
    ) -> BackgroundResponse:
        """
        Full-replace a background's BACKGROUND-source features, matched by id.

        Items carrying an ``id`` update that feature in place — the id is
        kept, so character grants and any player notes on them survive.
        Items without an ``id`` create new features; existing features
        whose id is absent from the payload are deleted, cascading their
        grants away. Runs atomically, then reconciles the grants of every
        character with this background so their builds match the new
        feature set.
        """

        background = await self._get_or_404(background_id)
        async with self._atomic():
            await replace_features_for_source(
                self.repository.db,
                FeatureSourceType.BACKGROUND,
                background.id,
                data.features,
                created_by_id,
                commit=False,
            )
            await reconcile_characters_for_source(self.repository.db, FeatureSourceType.BACKGROUND, background.id)

        await self._invalidate_cache()

        self.repository.db.expire(background)
        return self.response_schema.model_validate(await self._get_or_404(background_id))
