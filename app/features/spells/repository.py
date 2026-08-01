from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models.class_model import Class
from app.models.race_model import Race
from app.models.spell_model import Spell


class SpellRepository(BaseRepository[Spell]):
    def __init__(self, db: Session):
        super().__init__(Spell, db)

    def get_by_name(self, name: str) -> Spell | None:
        return self.db.query(Spell).filter(Spell.name == name).first()

    def get_all(self, *, skip: int = 0, limit: int = 100) -> list[Spell]:
        return (
            self.db.query(Spell)
            .options(
                selectinload(Spell.available_classes),
                selectinload(Spell.available_races),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_all_brief(self, *, skip: int = 0, limit: int = 100,
    ) -> list[Spell]:
        return (
            self.db.query(Spell)
            .options(
                selectinload(Spell.available_classes),
                selectinload(Spell.available_races),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_classes_by_ids(self, class_ids: list[int]) -> list[Class]:
        if not class_ids:
            return []
        return self.db.query(Class).filter(Class.id.in_(class_ids)).all()

    def get_races_by_ids(self, race_ids: list[int]) -> list[Race]:
        if not race_ids:
            return []
        return self.db.query(Race).filter(Race.id.in_(race_ids)).all()

    def set_classes(self, spell: Spell, classes: list[Class], *, commit: bool = True) -> Spell:
        """
        Replace all classes a spell is available to.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a spell + its class/race availability together)
        defer the commit and flush instead, without duplicating this
        method. See ``RaceRepository.set_ability_bonuses`` for the same
        pattern.
        """

        spell.available_classes = classes

        if commit:
            self.db.commit()
            self.db.refresh(spell)
        else:
            self.db.flush()

        return spell

    def set_races(self, spell: Spell, races: list[Race], *, commit: bool = True) -> Spell:
        """Replace all races a spell is available to. See ``set_classes`` for ``commit`` semantics."""

        spell.available_races = races

        if commit:
            self.db.commit()
            self.db.refresh(spell)
        else:
            self.db.flush()

        return spell
