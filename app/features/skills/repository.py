from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.background_association_models import background_skills
from app.models.character_association_models import CharacterSkillProficiency
from app.models.class_association_models import class_available_skills
from app.models.race_association_models import race_skills
from app.models.skill_model import Skill


class SkillRepository(BaseRepository[Skill]):
    def __init__(self, db: Session):
        super().__init__(Skill, db, search_fields=["name", "key"], unique_fields=["name", "key"])

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        if not skill_ids:
            return []
        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def is_in_use(self, skill_id: int) -> bool:
        """
        Check whether the skill is currently referenced anywhere that would
        block deletion at the DB level via ON DELETE RESTRICT: granted by a
        race (race_skills), available to a class (class_available_skills),
        granted by a background (background_skills), or held as a
        proficiency by a character (character_skill_proficiencies).
        """
        query = select(
            or_(
                exists().where(race_skills.c.skill_id == skill_id),
                exists().where(class_available_skills.c.skill_id == skill_id),
                exists().where(background_skills.c.skill_id == skill_id),
                exists().where(CharacterSkillProficiency.skill_id == skill_id),
            )
        )
        return bool(self.db.execute(query).scalar())
