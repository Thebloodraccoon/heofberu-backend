"""Background CRUD service including granted-skill management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cached_service import CachedService
from app.features.backgrounds.repository import BackgroundRepository
from app.features.backgrounds.schemas import (
    BackgroundCreate,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
)
from app.features.features.mixins import SourceFeatureMixin
from app.features.features.service import FeatureService
from app.features.skills.mixins import SkillsManagerMixin
from app.models.background_model import Background


class BackgroundService(
    SkillsManagerMixin,
    SourceFeatureMixin,
    CachedService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, BackgroundGetAllResponse],
):
    """
    Background-specific CRUD service built on :class:`CachedService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - management of granted skills, which live in their own association
        table (``background_skills``) and have no generic base-class
        equivalent. ``create_background`` can optionally set them up
        front, in the same transaction as the background itself;
      - per-source feature CRUD (``add_feature``/``update_feature``/
        ``remove_feature``) inherited from :class:`SourceFeatureMixin`.

    Unlike ``RaceService``, deletion is *not* blocked by characters
    bearing the background: its FK on ``characters.background_id`` is
    ``ON DELETE SET NULL``, so deleting a background in use simply
    detaches it from any characters. It IS blocked (409) once one of the
    background's features has been granted to a character — those grants
    live in ``character_features`` and must be revoked first, see
    ``BackgroundRepository.is_in_use``.

    ``get_by_id`` and ``get_all`` are inherited unchanged from
    ``CachedService``. The listing falls back to the eager-loaded
    ``repository.get_all`` because ``BackgroundGetAllResponse`` contains
    the ``granted_skills`` relationship, which the base column-select path
    cannot load. Listing and detail reads are cached via ``@use_cache``;
    because a background's writes also touch the ``features`` table
    (BACKGROUND-source rows), the service invalidates both its own
    namespace and ``features``.
    """

    repository: BackgroundRepository

    cache_namespaces = ("backgrounds", "features")

    _feature_source_type = FeatureSourceType.BACKGROUND

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            get_all_schema=BackgroundGetAllResponse,
        )
        self._features = FeatureService(db)

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
        ``FeatureService.create_features_for_source`` with
        ``source_type=BACKGROUND``.
        """

        skills = await self._resolve_skills(background_data.granted_skills)

        payload = background_data.model_dump(exclude={"granted_skills", "features"})
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if skills:
                await self.repository.set_skills(item, skills, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.BACKGROUND,
                item.id,
                background_data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return await self._get_response(item.id)
