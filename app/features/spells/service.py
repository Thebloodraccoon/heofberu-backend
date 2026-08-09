"""Spell CRUD service with transactional class/race availability setup."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.spells.repository import SpellRepository
from app.features.spells.schemas import (
    ClassAvailabilityUpdate,
    RaceAvailabilityUpdate,
    SpellCreate,
    SpellGetAllResponse,
    SpellResponse,
    SpellUpdate,
)
from app.models.spell_model import Spell


class SpellService(BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellGetAllResponse]):
    """
    Spell-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - the inherited paginated ``get_all`` (ordered by ``Spell.id``,
        searchable on ``name``), served as a lightweight ``Page`` cached
        transparently in Redis via ``@use_cache``;
      - a uniqueness check on ``name`` before create/update;
      - management of class/race availability, which lives in its own
        association tables (``spell_classes`` / ``spell_races``) and has no
        generic base-class equivalent. ``create_spell`` can optionally set
        both up front, in the same transaction as the spell itself. An
        empty (or omitted) list on either side means the spell is
        unrestricted for that dimension.
    """

    repository: SpellRepository

    cache_namespaces = ("spells",)

    def __init__(self, db: Session):
        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
            get_all_schema=SpellGetAllResponse,
        )

    @use_cache()
    def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[SpellGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    def get_by_id(self, item_id: int) -> SpellResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return super().get_by_id(item_id)

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
        self._invalidate_cache()

        return self.response_schema.model_validate(item)

    def set_classes(self, spell_id: int, data: ClassAvailabilityUpdate) -> SpellResponse:
        """Fully replace the classes a spell is available to. Empty list = unrestricted."""

        spell = self._get_or_404(spell_id)
        classes = self.resolve_ids(self.repository.get_classes_by_ids, data.class_ids, "Classes")

        updated_spell = self.repository.set_classes(spell, classes)
        self._invalidate_cache()

        return self.response_schema.model_validate(updated_spell)

    def set_races(self, spell_id: int, data: RaceAvailabilityUpdate) -> SpellResponse:
        """Fully replace the races a spell is available to. Empty list = unrestricted."""

        spell = self._get_or_404(spell_id)
        races = self.resolve_ids(self.repository.get_races_by_ids, data.race_ids, "Races")

        updated_spell = self.repository.set_races(spell, races)
        self._invalidate_cache()

        return self.response_schema.model_validate(updated_spell)
