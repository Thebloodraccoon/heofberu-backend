from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.spells.exceptions import SpellNameAlreadyExistsException, SpellNotFoundException
from app.features.spells.repository import SpellRepository
from app.features.spells.schemas import SpellBriefResponse, SpellCreate, SpellResponse, SpellUpdate
from app.models.spell_model import Spell


class SpellService(BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellBriefResponse]):
    """
    Spell-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a plain, unpaginated ``get_all`` (spells are listed in full, sorted
        by name, via ``SpellRepository.get_all``);
      - a uniqueness check on ``name`` before create/update.
    """

    repository: SpellRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
            not_found_exception_factory=lambda spell_id: SpellNotFoundException(spell_id=spell_id),
            brief_schema=SpellBriefResponse,
        )

    def create_spell(self, spell_data: SpellCreate) -> SpellResponse:
        """Create a spell after checking its name isn't already taken."""

        self._check_name_available(spell_data.name)
        return self.create(spell_data)

    def update_spell(self, spell_id: int, update_data: SpellUpdate) -> SpellResponse:
        """Update a spell, re-checking name uniqueness if the name is changing."""

        def check_name_available_if_changing(spell: Spell, fields: dict) -> None:
            if "name" in fields and fields["name"] != spell.name:
                self._check_name_available(fields["name"])

        return self.update(spell_id, update_data, before_update=check_name_available_if_changing)

    def _check_name_available(self, name: str) -> None:
        """Raise ``SpellNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise SpellNameAlreadyExistsException(name)
