from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.backgrounds.exceptions import (
    BackgroundNameAlreadyExistsException,
    BackgroundNotFoundException,
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
            not_found_exception_factory=lambda background_id: BackgroundNotFoundException(background_id=background_id),
            brief_schema=BackgroundBriefResponse,
        )
        self.db = db

    def list_brief(self, skip: int = 0, limit: int = 100) -> list[BackgroundBriefResponse]:
        """
        Return a paginated, lightweight listing of backgrounds.

        Overrides ``BaseService.list_brief`` because ``granted_skills`` is
        a relationship, not a column, and can't be selected via the
        generic ``db.query(Background.name, ...)`` approach the base
        class uses.
        """

        items = self.db.query(Background).order_by(Background.id).offset(skip).limit(limit).all()
        return [self.brief_schema.model_validate(item) for item in items]

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

        self._check_name_available(background_data.name)

        skills = None
        if background_data.granted_skills:
            skills, missing_ids = self._resolve_skill_ids(background_data.granted_skills)
            if missing_ids:
                raise InvalidSkillIdsException(missing_ids)

        payload = background_data.model_dump(exclude={"granted_skills"})
        payload["created_by_id"] = created_by_id

        try:
            with self.db.begin_nested():
                item = self.repository.create(payload, commit=False)

                if skills:
                    self.repository.set_skills(item, skills, commit=False)

            self.db.commit()
            self.db.refresh(item)
        except Exception:
            self.db.rollback()
            raise

        return self.response_schema.model_validate(item)

    def update_background(self, background_id: int, update_data: BackgroundUpdate) -> BackgroundResponse:
        """Update a background, re-checking name uniqueness if the name is changing."""

        def check_name_available_if_changing(background: Background, fields: dict) -> None:
            if "name" in fields and fields["name"] != background.name:
                self._check_name_available(fields["name"])

        return self.update(background_id, update_data, before_update=check_name_available_if_changing)

    def set_skills(self, background_id: int, data: SkillsUpdate) -> BackgroundResponse:
        """Fully replace the skills granted by a background."""

        background = self._get_or_404(background_id)

        skills, missing_ids = self._resolve_skill_ids(data.skill_ids)
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_background = self.repository.set_skills(background, skills)
        return self.response_schema.model_validate(updated_background)

    def _check_name_available(self, name: str) -> None:
        """Raise ``BackgroundNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise BackgroundNameAlreadyExistsException(name)

    def _resolve_skill_ids(self, skill_ids: list[int]):
        """Look up skills by id, returning (found_skills, missing_ids)."""

        skills = self.repository.get_skills_by_ids(skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in skill_ids if skill_id not in found_ids]
        return skills, missing_ids
