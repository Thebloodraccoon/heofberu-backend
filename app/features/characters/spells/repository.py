"""Character spell repository: slots and known spells."""

from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.character_association_models import CharacterSpellSlot
from app.models.character_spell_model import CharacterSpell
from app.models.spell_model import Spell


class CharacterSpellRepository(BaseRepository[CharacterSpellSlot]):
    """
    Repository for a character's spell slots and known spells.

    Split out of ``CharacterRepository`` — these are two related but
    separate tables (``character_spell_slots``, ``character_spells``)
    under the "what a character can cast" sub-domain, unrelated to the
    ``Character`` row's own columns. Bound to ``CharacterSpellSlot`` as
    its primary model.
    """

    def __init__(self, db: Session):
        super().__init__(CharacterSpellSlot, db)

    def get_spell_slot(self, character_id: int, level: str) -> CharacterSpellSlot | None:
        """Fetch a character's spell slot entry for a level, or None."""
        return (
            self.db.query(CharacterSpellSlot)
            .filter(
                CharacterSpellSlot.character_id == character_id,
                CharacterSpellSlot.spell_level == level,
            )
            .first()
        )

    def upsert_spell_slot(
        self, character_id: int, level: str, total: int | None, used: int | None
    ) -> CharacterSpellSlot:
        """
        Create or update the spell slot entry for a given level.

        If the entry doesn't exist yet, it's created with the given values
        (defaulting missing fields to 0). Validation of the used<=total
        invariant happens in the service before this is called.
        """

        slot = self.get_spell_slot(character_id, level)
        if slot is None:
            slot = CharacterSpellSlot(
                character_id=character_id,
                spell_level=level,
                total=total if total is not None else 0,
                used=used if used is not None else 0,
            )
            self.db.add(slot)
        else:
            if total is not None:
                slot.total = total
            if used is not None:
                slot.used = used

        self.db.commit()
        self.db.refresh(slot)
        return slot

    def get_all_spell_slots(self, character_id: int) -> list[CharacterSpellSlot]:
        """List all of a character's spell slot entries."""
        return self.db.query(CharacterSpellSlot).filter(CharacterSpellSlot.character_id == character_id).all()

    def apply_spell_slot_progression(
        self, character_id: int, slots_by_level: dict[str, int]
    ) -> list[CharacterSpellSlot]:
        """
        Sync a character's actual ``CharacterSpellSlot.total`` values to
        match ``slots_by_level`` (as returned by
        ``ClassRepository.get_spell_slot_progression`` for the character's
        current class/level).

        For each level in ``slots_by_level``: upsert the slot row, setting
        ``total`` to the given value. ``used`` is left untouched unless it
        would exceed the new ``total``, in which case it's clamped down to
        ``total`` (so the ``used <= total`` invariant always holds — this
        can only ever reduce ``used``, never invent slots as "spent").

        For any level the character currently has a row for but that is
        *not* present in ``slots_by_level`` (e.g. leveling down, or
        switching to a class that doesn't grant that level): the row's
        ``total`` is set to 0 and ``used`` is clamped to 0 with it, rather
        than deleted — this keeps history/ordering stable and matches
        ``upsert_spell_slot``'s "0 total = no slots" convention elsewhere.

        Levels never granted and not currently present in the character's
        rows are left alone (no zero-row is created for them).
        """

        existing = {slot.spell_level: slot for slot in self.get_all_spell_slots(character_id)}

        for level, total in slots_by_level.items():
            slot = existing.get(level)
            if slot is None:
                self.db.add(
                    CharacterSpellSlot(
                        character_id=character_id,
                        spell_level=level,
                        total=total,
                        used=0,
                    )
                )
            else:
                slot.total = total
                if slot.used > total:
                    slot.used = total

        for level, slot in existing.items():
            if level not in slots_by_level:
                slot.total = 0
                slot.used = 0

        self.db.commit()
        return self.get_all_spell_slots(character_id)

    def reset_all_spell_slots(self, character_id: int) -> None:
        """Set used=0 for every spell slot entry of the character (long rest)."""

        self.db.query(CharacterSpellSlot).filter(CharacterSpellSlot.character_id == character_id).update(
            {CharacterSpellSlot.used: 0}
        )
        self.db.commit()

    def get_known_spells(self, character_id: int) -> list[CharacterSpell]:
        """List all spells known by the character."""
        return self.db.query(CharacterSpell).filter(CharacterSpell.character_id == character_id).all()

    def get_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell | None:
        """Fetch a single known-spell entry, or None if not present."""
        return (
            self.db.query(CharacterSpell)
            .filter(
                CharacterSpell.character_id == character_id,
                CharacterSpell.spell_id == spell_id,
            )
            .first()
        )

    def add_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell:
        """Add a spell to the character's known spells."""
        character_spell = CharacterSpell(character_id=character_id, spell_id=spell_id)
        self.db.add(character_spell)
        self.db.commit()
        self.db.refresh(character_spell)
        return character_spell

    def remove_known_spell(self, character_spell: CharacterSpell) -> bool:
        """Remove a spell from the character's known spells."""
        self.db.delete(character_spell)
        self.db.commit()
        return True

    def count_known_spells_at_level(self, character_id: int, level: str) -> int:
        """
        Count how many spells the character already knows at a given
        ``Spell.level`` — compared against ``CharacterSpellSlot.total``
        for that level to cap how many spells of that level can be known
        at once. See ``CharacterSpellEligibilityChecker``.
        """

        return (
            self.db.query(CharacterSpell)
            .join(Spell, Spell.id == CharacterSpell.spell_id)
            .filter(
                CharacterSpell.character_id == character_id,
                Spell.level == level,
            )
            .count()
        )
