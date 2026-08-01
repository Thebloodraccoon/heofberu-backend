from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.spells.exceptions import (
    InvalidClassIdsException,
    InvalidRaceIdsException,
    SpellNameAlreadyExistsException,
    SpellNotFoundException,
)
from app.features.spells.repository import SpellRepository
from app.features.spells.schemas import (
    ClassAvailabilityUpdate,
    RaceAvailabilityUpdate,
    SpellBriefResponse,
    SpellCreate,
    SpellResponse,
    SpellUpdate,
)
from app.models.spell_model import Spell


class SpellService(BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellBriefResponse]):
    """
    Spell-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a plain, unpaginated ``get_all`` (spells are listed in full, sorted
        by name, via ``SpellRepository.get_all``);
      - a uniqueness check on ``name`` before create/update;
      - management of class/race availability, which lives in its own
        association tables (``spell_classes`` / ``spell_races``) and has no
        generic base-class equivalent. ``create_spell`` can optionally set
        both up front, in the same transaction as the spell itself. An
        empty (or omitted) list on either side means the spell is
        unrestricted for that dimension.
    """

    repository: SpellRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
            not_found_exception_factory=lambda spell_id: SpellNotFoundException(spell_id=spell_id),
            brief_schema=SpellBriefResponse,
        )
        self.db = db

    def list_brief(self, skip: int = 0, limit: int = 100) -> list[SpellBriefResponse]:
        """
        Return a paginated, lightweight listing of spells.

        Overrides ``BaseService.list_brief``: the generic base builds its
        query by selecting individual columns named after
        ``brief_schema``'s fields (``db.query(Spell.name, Spell.school,
        ...)``), which only works for plain scalar columns. ``available_classes``
        / ``available_races`` are relationships (backed by the
        ``spell_classes`` / ``spell_races`` association tables), not
        columns, so they can't be selected that way — this override loads
        full ``Spell`` rows (with those relationships eagerly joined)
        instead, and lets Pydantic pick out just the brief fields.
        """

        items = self.db.query(Spell).order_by(Spell.id).offset(skip).limit(limit).all()
        return [self.brief_schema.model_validate(item) for item in items]

    def create_spell(self, spell_data: SpellCreate) -> SpellResponse:
        """
        Create a spell after checking its name isn't already taken.

        ``spell_data.available_classes`` / ``available_races`` are
        optional. If supplied, they're set in the *same transaction* as
        the spell itself, mirroring ``RaceService.create_race``. Every
        write inside the nested transaction below passes ``commit=False``
        for the same reason documented there: a plain ``session.commit()``
        from any of them would commit the entire outer transaction, not
        just the ``begin_nested()`` SAVEPOINT.
        """

        self._check_name_available(spell_data.name)

        classes = None
        if spell_data.available_classes:
            classes, missing_ids = self._resolve_class_ids(spell_data.available_classes)
            if missing_ids:
                raise InvalidClassIdsException(missing_ids)

        races = None
        if spell_data.available_races:
            races, missing_ids = self._resolve_race_ids(spell_data.available_races)
            if missing_ids:
                raise InvalidRaceIdsException(missing_ids)

        payload = spell_data.model_dump(exclude={"available_classes", "available_races"})

        try:
            with self.db.begin_nested():
                item = self.repository.create(payload, commit=False)

                if classes:
                    self.repository.set_classes(item, classes, commit=False)

                if races:
                    self.repository.set_races(item, races, commit=False)

            self.db.commit()
            self.db.refresh(item)
        except Exception:
            self.db.rollback()
            raise

        return self.response_schema.model_validate(item)

    def update_spell(self, spell_id: int, update_data: SpellUpdate) -> SpellResponse:
        """Update a spell, re-checking name uniqueness if the name is changing."""

        def check_name_available_if_changing(spell: Spell, fields: dict) -> None:
            if "name" in fields and fields["name"] != spell.name:
                self._check_name_available(fields["name"])

        return self.update(spell_id, update_data, before_update=check_name_available_if_changing)

    def set_classes(self, spell_id: int, data: ClassAvailabilityUpdate) -> SpellResponse:
        """Fully replace the classes a spell is available to. Empty list = unrestricted."""

        spell = self._get_or_404(spell_id)

        classes, missing_ids = self._resolve_class_ids(data.class_ids)
        if missing_ids:
            raise InvalidClassIdsException(missing_ids)

        updated_spell = self.repository.set_classes(spell, classes)
        return self.response_schema.model_validate(updated_spell)

    def set_races(self, spell_id: int, data: RaceAvailabilityUpdate) -> SpellResponse:
        """Fully replace the races a spell is available to. Empty list = unrestricted."""

        spell = self._get_or_404(spell_id)

        races, missing_ids = self._resolve_race_ids(data.race_ids)
        if missing_ids:
            raise InvalidRaceIdsException(missing_ids)

        updated_spell = self.repository.set_races(spell, races)
        return self.response_schema.model_validate(updated_spell)

    def _check_name_available(self, name: str) -> None:
        """Raise ``SpellNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise SpellNameAlreadyExistsException(name)

    def _resolve_class_ids(self, class_ids: list[int]):
        """Look up classes by id, returning (found_classes, missing_ids)."""

        classes = self.repository.get_classes_by_ids(class_ids)
        found_ids = {c.id for c in classes}
        missing_ids = [class_id for class_id in class_ids if class_id not in found_ids]
        return classes, missing_ids

    def _resolve_race_ids(self, race_ids: list[int]):
        """Look up races by id, returning (found_races, missing_ids)."""

        races = self.repository.get_races_by_ids(race_ids)
        found_ids = {r.id for r in races}
        missing_ids = [race_id for race_id in race_ids if race_id not in found_ids]
        return races, missing_ids
