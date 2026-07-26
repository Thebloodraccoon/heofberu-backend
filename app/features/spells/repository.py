from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.models.spell_model import Spell


class SpellRepository(BaseRepository[Spell]):
    def __init__(self, db: Session):
        super().__init__(Spell, db)

    def get_all(self) -> list[Spell]:
        """Get all spells, ordered by name (overrides base pagination-based get_all)."""
        return self.db.query(Spell).order_by(Spell.name).all()

    def get_by_name(self, name: str) -> Spell | None:
        return self.db.query(Spell).filter(Spell.name == name).first()
