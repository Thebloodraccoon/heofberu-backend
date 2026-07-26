from sqlalchemy.orm import Session

from app.exceptions.race_exceptions import (
    InvalidSkillIdsException,
    RaceNameAlreadyExistsException,
    RaceNotFoundException,
)
from app.features.races.repository import RaceRepository
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceResponse,
    RaceUpdate,
    SkillsUpdate,
)


class RaceService:
    def __init__(self, db: Session):
        self.repository = RaceRepository(db)

    def get_all_races(self) -> list[RaceResponse]:
        races = self.repository.get_all()
        return [RaceResponse.model_validate(race) for race in races]

    def get_race_by_id(self, race_id: int) -> RaceResponse:
        race = self.repository.get_by_id(race_id)
        if not race:
            raise RaceNotFoundException(race_id=race_id)

        return RaceResponse.model_validate(race)

    def create_race(self, race_data: RaceCreate) -> RaceResponse:
        self._check_name_available(race_data.name)

        race = self.repository.create(race_data.model_dump())
        return RaceResponse.model_validate(race)

    def update_race(self, race_id: int, update_data: RaceUpdate) -> RaceResponse:
        race = self._get_race_or_404(race_id)

        fields = update_data.model_dump(exclude_unset=True)

        if "name" in fields and fields["name"] != race.name:
            self._check_name_available(fields["name"])

        updated_race = self.repository.update(race, fields)
        return RaceResponse.model_validate(updated_race)

    def delete_race(self, race_id: int) -> bool:
        race = self._get_race_or_404(race_id)
        return self.repository.delete(race)

    def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses."""
        race = self._get_race_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        updated_race = self.repository.set_ability_bonuses(race, bonuses)
        return RaceResponse.model_validate(updated_race)

    def set_skills(self, race_id: int, data: SkillsUpdate) -> RaceResponse:
        """Fully replace the skills granted by a race."""
        race = self._get_race_or_404(race_id)

        skills = self.repository.get_skills_by_ids(data.skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in data.skill_ids if skill_id not in found_ids]
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_race = self.repository.set_skills(race, skills)
        return RaceResponse.model_validate(updated_race)

    def _get_race_or_404(self, race_id: int):
        race = self.repository.get_by_id(race_id)
        if not race:
            raise RaceNotFoundException(race_id=race_id)
        return race

    def _check_name_available(self, name: str) -> None:
        if self.repository.get_by_name(name):
            raise RaceNameAlreadyExistsException(name)