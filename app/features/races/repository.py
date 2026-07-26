from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.models.race_association_models import RaceAbilityBonus
from app.models.race_model import Race
from app.models.skill_model import Skill


class RaceRepository(BaseRepository[Race]):
    def __init__(self, db: Session):
        super().__init__(Race, db)

    def get_all(self) -> list[Race]:
        """Get all races, ordered by name (overrides base pagination-based get_all)."""
        return self.db.query(Race).order_by(Race.name).all()

    def get_by_name(self, name: str) -> Race | None:
        return self.db.query(Race).filter(Race.name == name).first()

    def set_ability_bonuses(self, race: Race, bonuses: list[dict]) -> Race:
        """Replace all ability bonuses for a race with the given list."""
        self.db.query(RaceAbilityBonus).filter(RaceAbilityBonus.race_id == race.id).delete()

        for item in bonuses:
            self.db.add(RaceAbilityBonus(race_id=race.id, ability=item["ability"], bonus=item["bonus"]))

        self.db.commit()
        self.db.refresh(race)
        return race

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        if not skill_ids:
            return []
        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def set_skills(self, race: Race, skills: list[Skill]) -> Race:
        """Replace all granted skills for a race with the given list."""
        race.granted_skills = skills
        self.db.commit()
        self.db.refresh(race)
        return race
