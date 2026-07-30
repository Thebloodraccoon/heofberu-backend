from sqlalchemy.orm import Session

from app.core.service import BaseService
from app.features.races.exceptions import (
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
from app.models.race_model import Race


class RaceService(BaseService[Race, RaceCreate, RaceUpdate, RaceResponse]):
    """
    Race-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a plain, unpaginated ``get_all`` (races are listed in full, sorted
        by name, via ``RaceRepository.get_all``);
      - a uniqueness check on ``name`` before create/update;
      - management of ability bonuses and granted skills, which live in
        their own association tables and have no generic base-class
        equivalent.
    """

    def __init__(self, db: Session):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            not_found_exception_factory=lambda race_id: RaceNotFoundException(race_id=race_id),
        )
        self.repository: RaceRepository

    def get_race_by_id(self, race_id: int) -> RaceResponse:
        """Return a single race by ID, or raise ``RaceNotFoundException``."""

        return self.get_by_id(race_id)

    def create_race(self, race_data: RaceCreate, created_by_id: int | None = None) -> RaceResponse:
        """
        Create a race after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew races) and is not part of ``RaceCreate`` itself, since
        it comes from the authenticated user, not client input.
        """

        self._check_name_available(race_data.name)

        payload = race_data.model_dump()
        payload["created_by_id"] = created_by_id

        item = self.repository.create(payload)
        return self.response_schema.model_validate(item)

    def update_race(self, race_id: int, update_data: RaceUpdate) -> RaceResponse:
        """Update a race, re-checking name uniqueness if the name is changing."""

        race = self._get_or_404(race_id)
        fields = update_data.model_dump(exclude_unset=True)

        if "name" in fields and fields["name"] != race.name:
            self._check_name_available(fields["name"])

        return self.update(race_id, update_data)

    def delete_race(self, race_id: int) -> bool:
        """Delete a race by ID, or raise ``RaceNotFoundException``."""

        return self.delete(race_id)

    def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses."""
        race = self._get_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        updated_race = self.repository.set_ability_bonuses(race, bonuses)
        return self.response_schema.model_validate(updated_race)

    def set_skills(self, race_id: int, data: SkillsUpdate) -> RaceResponse:
        """Fully replace the skills granted by a race."""
        race = self._get_or_404(race_id)

        skills = self.repository.get_skills_by_ids(data.skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in data.skill_ids if skill_id not in found_ids]
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_race = self.repository.set_skills(race, skills)
        return self.response_schema.model_validate(updated_race)

    def _check_name_available(self, name: str) -> None:
        """Raise ``RaceNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise RaceNameAlreadyExistsException(name)
