from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.models.class_association_models import class_available_skills
from app.models.race_association_models import race_skills
from app.models.skill_model import Skill


class SkillRepository(BaseRepository[Skill]):
    def __init__(self, db: Session):
        super().__init__(Skill, db)

    def get_all(self) -> list[Skill]:
        """Get all skills, ordered by name (overrides base pagination-based get_all)."""
        return self.db.query(Skill).order_by(Skill.name).all()

    def get_by_key(self, key: str) -> Skill | None:
        return self.db.query(Skill).filter(Skill.key == key).first()

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        if not skill_ids:
            return []
        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def is_in_use(self, skill_id: int) -> bool:
        """
        Check whether the skill is currently referenced by any race
        (race_skills) or class (class_available_skills), either of which would
        block deletion at the DB level via ON DELETE RESTRICT.
        """
        used_by_race = self.db.query(race_skills).filter(race_skills.c.skill_id == skill_id).first() is not None
        if used_by_race:
            return True

        return (
            self.db.query(class_available_skills).filter(class_available_skills.c.skill_id == skill_id).first()
            is not None
        )
