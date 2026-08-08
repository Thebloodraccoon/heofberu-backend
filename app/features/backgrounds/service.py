"""Background CRUD service including granted-skill management."""

from typing import Any

from sqlalchemy.orm import Session

from app.constants import FeatureSourceType
from app.core.base_service import BaseService, Page, paginate
from app.features.backgrounds.repository import BackgroundRepository
from app.features.backgrounds.schemas import (
    BackgroundBriefResponse,
    BackgroundCreate,
    BackgroundResponse,
    BackgroundUpdate,
    SkillsUpdate,
)
from app.features.features.service import create_features_for_source
from app.models.background_model import Background


class BackgroundService(
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, BackgroundBriefResponse]
):
    """
    Background-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - management of granted skills, which live in their own association
        table (``background_skills``) and have no generic base-class
        equivalent. ``create_background`` can optionally set them up
        front, in the same transaction as the background itself.

    Unlike ``RaceService``, there is no in-use delete guard: a
    background's FK on ``characters.background_id`` is ``ON DELETE SET
    NULL``, so deleting a background in use simply detaches it from any
    characters rather than being blocked — the inherited ``delete`` is
    used as-is, no ``delete_background`` override needed.

    ``get_by_id`` and ``list_brief`` are inherited unchanged from
    ``BaseService``. Note that the inherited ``list_brief`` derives its
    columns from ``BackgroundBriefResponse``'s field names, which include
    the ``granted_skills`` relationship — unlike brief schemas made up of
    plain columns only.
    """

    repository: BackgroundRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            brief_schema=BackgroundBriefResponse,
        )

    def list_brief(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[BackgroundBriefResponse]:
        """
        Overridden because ``BackgroundBriefResponse.granted_skills`` is a
        relationship, which the base column-select ``list_brief`` cannot
        load (the base now raises ``NotImplementedError`` for such fields).

        Uses ``repository.get_all`` instead — its ``default_load_options``
        (``selectinload(Background.granted_skills)``) eager-loads the
        skills, so every row carries ``granted_skills`` without an N+1.
        """

        skip, limit = paginate(page, size)
        items = self.repository.get_all(skip=skip, limit=limit, filters=filters, search=search)
        total = self.repository.count(filters=filters, search=search)

        return Page(
            items=[BackgroundBriefResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            size=size,
        )

    def create_background(
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
            self.resolve_ids(
                self.repository.get_skills_by_ids,
                background_data.granted_skills,
                "Skills",
            )
            if background_data.granted_skills
            else None
        )

        payload = background_data.model_dump(exclude={"granted_skills", "features"})
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if skills:
                self.repository.set_skills(item, skills, commit=False)

            create_features_for_source(
                self.repository.db,
                FeatureSourceType.BACKGROUND,
                item.id,
                background_data.features,
                created_by_id,
                commit=False,
            )

        self.repository.refresh(item)

        return self.response_schema.model_validate(item)

    def set_skills(self, background_id: int, data: SkillsUpdate) -> BackgroundResponse:
        """Fully replace the skills granted by a background."""

        background = self._get_or_404(background_id)

        skills = self.resolve_ids(self.repository.get_skills_by_ids, data.skill_ids, "Skills")

        updated_background = self.repository.set_skills(background, skills)
        return self.response_schema.model_validate(updated_background)
