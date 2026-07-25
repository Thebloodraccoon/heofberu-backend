from sqlalchemy.orm import Session

from app.models.spell_model import Spell


class SpellRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Spell]:
        return self.db.query(Spell).order_by(Spell.name).all()

    def get_by_id(self, spell_id: int) -> Spell | None:
        return self.db.query(Spell).filter(Spell.id == spell_id).first()

    def get_by_name(self, name: str) -> Spell | None:
        return self.db.query(Spell).filter(Spell.name == name).first()

    def create(self, spell_data: dict) -> Spell:
        spell = Spell(**spell_data)
        self.db.add(spell)
        self.db.commit()
        self.db.refresh(spell)
        return spell

    def update(self, spell: Spell, update_data: dict) -> Spell:
        for field, value in update_data.items():
            setattr(spell, field, value)

        self.db.commit()
        self.db.refresh(spell)
        return spell
