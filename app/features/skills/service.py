from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions.skill_exceptions import (
    SkillInUseException,
    SkillKeyAlreadyExistsException,
    SkillNotFoundException,
)
from app.features.skills.repository import SkillRepository
from app.features.skills.schemas import SkillCreate, SkillResponse, SkillUpdate


class SkillService:
    def __init__(self, db: Session):
        self.repository = SkillRepository(db)

    def get_all_skills(self) -> list[SkillResponse]:
        skills = self.repository.get_all()
        return [SkillResponse.model_validate(skill) for skill in skills]

    def get_skill_by_id(self, skill_id: int) -> SkillResponse:
        skill = self._get_skill_or_404(skill_id)
        return SkillResponse.model_validate(skill)

    def create_skill(self, skill_data: SkillCreate) -> SkillResponse:
        self._check_key_available(skill_data.key)

        skill = self.repository.create(skill_data.model_dump())
        return SkillResponse.model_validate(skill)

    def update_skill(self, skill_id: int, update_data: SkillUpdate) -> SkillResponse:
        skill = self._get_skill_or_404(skill_id)

        fields = update_data.model_dump(exclude_unset=True)

        if "key" in fields and fields["key"] != skill.key:
            self._check_key_available(fields["key"])

        updated_skill = self.repository.update(skill, fields)
        return SkillResponse.model_validate(updated_skill)

    def delete_skill(self, skill_id: int) -> bool:
        skill = self._get_skill_or_404(skill_id)

        if self.repository.is_in_use(skill_id):
            raise SkillInUseException(skill_id=skill_id)

        try:
            return self.repository.delete(skill)
        except IntegrityError:
            # Safety net in case of a race condition between the check above
            # and the actual delete (the FK is ON DELETE RESTRICT).
            self.repository.db.rollback()
            raise SkillInUseException(skill_id=skill_id)

    def _get_skill_or_404(self, skill_id: int):
        skill = self.repository.get_by_id(skill_id)
        if not skill:
            raise SkillNotFoundException(skill_id=skill_id)
        return skill

    def _check_key_available(self, key: str) -> None:
        if self.repository.get_by_key(key):
            raise SkillKeyAlreadyExistsException(key)
