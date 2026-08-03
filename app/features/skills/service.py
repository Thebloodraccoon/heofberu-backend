from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.skills.exceptions import (
    SkillInUseException,
    SkillNotFoundException,
)
from app.features.skills.repository import SkillRepository
from app.features.skills.schemas import SkillBriefResponse, SkillCreate, SkillResponse, SkillUpdate
from app.models.skill_model import Skill


class SkillService(BaseService[Skill, SkillCreate, SkillUpdate, SkillResponse, SkillBriefResponse]):
    """
    Skill-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a plain, unpaginated ``get_all`` (skills are listed in full, sorted
        by name, via ``SkillRepository.get_all_sorted``);
      - a uniqueness check on ``key`` before create/update;
      - a delete guard that blocks removing a skill still referenced by any
        race, class, background, or character skill proficiency, since the
        FK on all four is ``ON DELETE RESTRICT``.
    """

    repository: SkillRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=SkillRepository(db),
            response_schema=SkillResponse,
            not_found_exception_factory=lambda skill_id: SkillNotFoundException(skill_id=skill_id),
            brief_schema=SkillBriefResponse,
        )

    def delete_skill(self, skill_id: int) -> bool:
        """
        Delete a skill by ID, raising ``SkillInUseException`` if it's still
        referenced by any race, class, background, or character skill
        proficiency.

        Raises the feature's not-found exception if ``skill_id`` doesn't
        exist. The in-use check happens before deletion, with an
        ``IntegrityError`` safety net in case of a race condition between
        the check and the actual delete (the FK is ``ON DELETE RESTRICT``).
        """

        skill = self._get_or_404(skill_id)

        if self.repository.is_in_use(skill_id):
            raise SkillInUseException(skill_id=skill_id)

        try:
            return self.repository.delete(skill)
        except IntegrityError:
            self.repository.db.rollback()
            raise SkillInUseException(skill_id=skill_id)
