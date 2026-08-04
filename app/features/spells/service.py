from sqlalchemy.orm import Session

from app.core.base_service import BaseService
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
            brief_schema=SpellBriefResponse,
        )

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

        classes = (
            self.resolve_ids(self.repository.get_classes_by_ids, spell_data.available_classes, "Classes")
            if spell_data.available_classes
            else None
        )
        races = (
            self.resolve_ids(self.repository.get_races_by_ids, spell_data.available_races, "Races")
            if spell_data.available_races
            else None
        )

        payload = spell_data.model_dump(exclude={"available_classes", "available_races"})

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if classes:
                self.repository.set_classes(item, classes, commit=False)

            if races:
                self.repository.set_races(item, races, commit=False)

        self.repository.refresh(item)

        return self.response_schema.model_validate(item)

    def set_classes(self, spell_id: int, data: ClassAvailabilityUpdate) -> SpellResponse:
        """Fully replace the classes a spell is available to. Empty list = unrestricted."""

        spell = self._get_or_404(spell_id)
        classes = self.resolve_ids(self.repository.get_classes_by_ids, data.class_ids, "Classes")

        updated_spell = self.repository.set_classes(spell, classes)
        return self.response_schema.model_validate(updated_spell)

    def set_races(self, spell_id: int, data: RaceAvailabilityUpdate) -> SpellResponse:
        """Fully replace the races a spell is available to. Empty list = unrestricted."""

        spell = self._get_or_404(spell_id)
        races = self.resolve_ids(self.repository.get_races_by_ids, data.race_ids, "Races")

        updated_spell = self.repository.set_races(spell, races)
        return self.response_schema.model_validate(updated_spell)
