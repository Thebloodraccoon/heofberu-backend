from sqlalchemy.orm import Session

from app.core.base_service import BaseService
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
            brief_schema=SkillBriefResponse,
        )
