from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.background_model import Background
from app.models.skill_model import Skill


class BackgroundRepository(BaseRepository[Background]):
    def __init__(self, db: Session):
        super().__init__(Background, db)

    def get_by_name(self, name: str) -> Background | None:
        return self.db.query(Background).filter(Background.name == name).first()

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        if not skill_ids:
            return []

        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def set_skills(self, background: Background, skills: list[Skill], *, commit: bool = True) -> Background:
        """
        Replace all granted skills for a background with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a background + its skills together) defer the
        commit and flush instead, without duplicating this method. See
        ``RaceRepository.set_skills`` for the same pattern.
        """

        background.granted_skills = skills

        if commit:
            self.db.commit()
            self.db.refresh(background)
        else:
            self.db.flush()

        return background
