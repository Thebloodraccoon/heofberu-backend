from sqlalchemy.orm import Session

from app.exceptions.spell_exceptions import SpellNameAlreadyExistsException, SpellNotFoundException
from app.features.spells.repository import SpellRepository
from app.features.spells.schemas import SpellCreate, SpellResponse, SpellUpdate


class SpellService:
    def __init__(self, db: Session):
        self.repository = SpellRepository(db)

    def get_all_spells(self) -> list[SpellResponse]:
        spells = self.repository.get_all()
        return [SpellResponse.model_validate(spell) for spell in spells]

    def get_spell_by_id(self, spell_id: int) -> SpellResponse:
        spell = self.repository.get_by_id(spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=spell_id)

        return SpellResponse.model_validate(spell)

    def create_spell(self, spell_data: SpellCreate) -> SpellResponse:
        self._check_name_available(spell_data.name)

        spell = self.repository.create(spell_data.model_dump())
        return SpellResponse.model_validate(spell)

    def update_spell(self, spell_id: int, update_data: SpellUpdate) -> SpellResponse:
        spell = self.repository.get_by_id(spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=spell_id)

        fields = update_data.model_dump(exclude_unset=True)

        if "name" in fields and fields["name"] != spell.name:
            self._check_name_available(fields["name"])

        updated_spell = self.repository.update(spell, fields)
        return SpellResponse.model_validate(updated_spell)

    def _check_name_available(self, name: str) -> None:
        if self.repository.get_by_name(name):
            raise SpellNameAlreadyExistsException(name)
