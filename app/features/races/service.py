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
    RaceBriefResponse,
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
      - a paginated ``list_brief`` for lightweight listing views;
      - a uniqueness check on ``name`` before create/update;
      - management of ability bonuses and granted skills, which live in
        their own association tables and have no generic base-class
        equivalent. ``create_race`` can optionally set them up front, in
        the same transaction as the race itself.
    """

    def __init__(self, db: Session):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            not_found_exception_factory=lambda race_id: RaceNotFoundException(race_id=race_id),
        )
        self.repository: RaceRepository
        self.db = db

    def get_race_by_id(self, race_id: int) -> RaceResponse:
        """Return a single race by ID, or raise ``RaceNotFoundException``."""

        return self.get_by_id(race_id)

    def list_brief(self, skip: int = 0, limit: int = 100) -> list[RaceBriefResponse]:
        """
        Return a paginated, lightweight listing of races.

        No ``ability_bonuses``/``granted_skills``/``traits``/``description``
        are loaded or serialized — use ``get_race_by_id`` for the full
        record when needed. Intended for list/dropdown-style UI where the
        full payload is wasted bandwidth.
        """

        items = self.repository.get_brief(skip=skip, limit=limit)
        return [RaceBriefResponse.model_validate(item) for item in items]

    def create_race(self, race_data: RaceCreate, created_by_id: int | None = None) -> RaceResponse:
        """
        Create a race after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew races) and is not part of ``RaceCreate`` itself, since
        it comes from the authenticated user, not client input.

        ``race_data.ability_bonuses`` / ``race_data.granted_skills`` are
        optional. If supplied, they're set in the *same transaction* as the
        race itself (base fields + bonuses + skills all commit together, or
        none do) — this is what lets a client create a fully-formed race in
        one request instead of one POST plus two PUTs.
        """

        self._check_name_available(race_data.name)

        if race_data.granted_skills:
            self._validate_skill_ids(race_data.granted_skills)

        payload = race_data.model_dump(exclude={"ability_bonuses", "granted_skills"})
        payload["created_by_id"] = created_by_id

        try:
            with self.db.begin_nested():
                item = self.repository.create(payload)

                if race_data.ability_bonuses:
                    bonuses = [
                        {"ability": b.ability, "bonus": b.bonus} for b in race_data.ability_bonuses
                    ]
                    self.repository.set_ability_bonuses(item, bonuses, commit=False)

                if race_data.granted_skills:
                    skills = self.repository.get_skills_by_ids(race_data.granted_skills)
                    item.granted_skills = skills
                    self.db.flush()

            self.db.commit()
            self.db.refresh(item)
        except Exception:
            self.db.rollback()
            raise

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

        skills, missing_ids = self._resolve_skill_ids(data.skill_ids)
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_race = self.repository.set_skills(race, skills)
        return self.response_schema.model_validate(updated_race)

    def _check_name_available(self, name: str) -> None:
        """Raise ``RaceNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise RaceNameAlreadyExistsException(name)

    def _resolve_skill_ids(self, skill_ids: list[int]):
        """Look up skills by id, returning (found_skills, missing_ids)."""

        skills = self.repository.get_skills_by_ids(skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in skill_ids if skill_id not in found_ids]
        return skills, missing_ids

    def _validate_skill_ids(self, skill_ids: list[int]) -> None:
        """Raise ``InvalidSkillIdsException`` if any id in ``skill_ids`` doesn't exist."""

        _, missing_ids = self._resolve_skill_ids(skill_ids)
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)
