from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.backgrounds.exceptions import (
    InvalidSkillIdsException,
)
from app.features.backgrounds.repository import BackgroundRepository
from app.features.backgrounds.schemas import (
    BackgroundBriefResponse,
    BackgroundCreate,
    BackgroundResponse,
    BackgroundUpdate,
    SkillsUpdate,
)
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
    ``BaseService``. ``list_brief`` derives its columns from
    ``BackgroundBriefResponse``'s field names — since ``granted_skills``
    is a relationship rather than a plain column, this override replaces
    the generic column-select query with one that loads full rows instead
    (see ``SpellService.list_brief`` for the same situation and reasoning).
    """

    repository: BackgroundRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            brief_schema=BackgroundBriefResponse,
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

        ``background_data.granted_skills`` is optional. If supplied, it's
        set in the *same transaction* as the background itself — base
        fields + skills commit together, or neither do. See
        ``RaceService.create_race`` for the same pattern and the reasoning
        behind every nested write passing ``commit=False``.
        """

        skills = (
            self._resolve_or_raise(
                self.repository.get_skills_by_ids,
                background_data.granted_skills,
                InvalidSkillIdsException,
            )
            if background_data.granted_skills
            else None
        )

        payload = background_data.model_dump(exclude={"granted_skills"})
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if skills:
                self.repository.set_skills(item, skills, commit=False)

        self.repository.refresh(item)

        return self.response_schema.model_validate(item)

    def set_skills(self, background_id: int, data: SkillsUpdate) -> BackgroundResponse:
        """Fully replace the skills granted by a background."""

        background = self._get_or_404(background_id)

        skills = self._resolve_or_raise(self.repository.get_skills_by_ids, data.skill_ids, InvalidSkillIdsException)

        updated_background = self.repository.set_skills(background, skills)
        return self.response_schema.model_validate(updated_background)
