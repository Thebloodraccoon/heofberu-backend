from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.races.exceptions import (
    InvalidSkillIdsException,
    RaceInUseException,
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


class RaceService(BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceBriefResponse]):
    """
    Race-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - a ``name``/``size`` ``search`` on top of listing, since
        ``BaseService.get_all``/``list_brief`` only know about exact-match
        ``filters`` and have no notion of a free-text search;
      - management of ability bonuses and granted skills, which live in
        their own association tables and have no generic base-class
        equivalent. ``create_race`` sets them up front, in the same
        transaction as the race itself, via ``BaseService._atomic()``;
      - a delete guard that blocks removing a race still assigned to any
        character, since the FK is ``ON DELETE RESTRICT``.

    ``get_by_id`` is inherited unchanged from ``BaseService`` — races add
    no behavior on top of it, so endpoints call it directly. ``get_all``
    and ``list_brief`` are overridden here (not left as pass-throughs)
    purely to add the ``search`` parameter; the pagination/filters/
    serialization logic underneath is still the base class's.
    ``delete`` is overridden as ``delete_race`` to add the in-use guard;
    endpoints should call ``delete_race``, not the inherited ``delete``.
    ``list_brief`` derives its columns from ``RaceBriefResponse``'s field
    names (id, name, size, is_homebrew) and is ordered by ``Race.id``.
    """

    repository: RaceRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            not_found_exception_factory=lambda race_id: RaceNotFoundException(race_id=race_id),
            brief_schema=RaceBriefResponse,
        )

    def create_race(self, race_data: RaceCreate, created_by_id: int | None = None) -> RaceResponse:
        """
        Create a race after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew races) and is not part of ``RaceCreate`` itself, since
        it comes from the authenticated user, not client input.

        ``race_data.ability_bonuses`` / ``race_data.granted_skills`` are
        optional. If supplied, they're set in the *same transaction* as the
        race itself (base fields + bonuses + skills all commit together, or
        none do) via ``BaseService._atomic()`` — this is what lets a client
        create a fully-formed race in one request instead of one POST plus
        two PUTs.

        Every write inside ``_atomic()`` passes ``commit=False`` —
        including ``repository.create`` itself — per the hazard documented
        on ``_atomic()``/``BaseRepository.create``.
        """

        self._check_name_available(race_data.name)

        skills = None
        if race_data.granted_skills:
            found = self.repository.get_skills_by_ids(race_data.granted_skills)
            skills, missing_ids = self.resolve_ids(found, race_data.granted_skills)
            if missing_ids:
                raise InvalidSkillIdsException(missing_ids)

        payload = race_data.model_dump(exclude={"ability_bonuses", "granted_skills"})
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if race_data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in race_data.ability_bonuses]
                self.repository.set_ability_bonuses(item, bonuses, commit=False)

            if skills:
                self.repository.set_skills(item, skills, commit=False)

        self.repository.refresh(item)
        return self.response_schema.model_validate(item)

    def update_race(self, race_id: int, update_data: RaceUpdate) -> RaceResponse:
        """Update a race, re-checking name uniqueness if the name is changing."""

        def check_name_available_if_changing(race: Race, fields: dict) -> None:
            if "name" in fields and fields["name"] != race.name:
                self._check_name_available(fields["name"])

        return self.update(race_id, update_data, before_update=check_name_available_if_changing)

    def delete_race(self, race_id: int) -> bool:
        """
        Delete a race by ID, raising ``RaceInUseException`` if it's still
        assigned to any character.

        Raises the feature's not-found exception if ``race_id`` doesn't
        exist. The in-use check happens before deletion, with an
        ``IntegrityError`` safety net in case of a race condition between
        the check and the actual delete (the FK is ``ON DELETE RESTRICT``).
        """
        race = self._get_or_404(race_id)

        if self.repository.is_in_use(race_id):
            raise RaceInUseException(race_id=race_id)

        try:
            return self.repository.delete(race)
        except IntegrityError:
            self.repository.db.rollback()
            raise RaceInUseException(race_id=race_id)

    def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses."""

        race = self._get_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        updated_race = self.repository.set_ability_bonuses(race, bonuses)
        return self.response_schema.model_validate(updated_race)

    def set_skills(self, race_id: int, data: SkillsUpdate) -> RaceResponse:
        """Fully replace the skills granted by a race."""

        race = self._get_or_404(race_id)

        found = self.repository.get_skills_by_ids(data.skill_ids)
        skills, missing_ids = self.resolve_ids(found, data.skill_ids)
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_race = self.repository.set_skills(race, skills)
        return self.response_schema.model_validate(updated_race)

    def _check_name_available(self, name: str) -> None:
        """Raise ``RaceNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise RaceNameAlreadyExistsException(name)
