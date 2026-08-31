"""Character spell repositories: spell slots and known spells."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.character_association_models import CharacterSpellSlot
from app.models.character_spell_model import CharacterSpell
from app.models.spell_model import Spell


class CharacterSpellSlotRepository(BaseRepository[CharacterSpellSlot]):
    """
    Repository for a character's spell slots (``character_spell_slots``).

    Split out of the old single ``CharacterSpellRepository``, which was
    bound to ``CharacterSpellSlot`` yet also handled known spells — this
    class owns only slot totals per level. Known spells live in the
    sibling ``CharacterSpellRepository``.

    Totals are written exclusively by :meth:`apply_spell_slot_progression`
    from the class/level progression table; there is no client-facing
    write path (no slot spending). The legacy ``used`` column is kept at
    0 for DB-constraint hygiene only.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterSpellSlot, db)

    async def get_spell_slot(self, character_id: int, level: str) -> CharacterSpellSlot | None:
        """Fetch a character's spell slot entry for a level, or None."""

        result = await self.db.execute(
            select(CharacterSpellSlot).where(
                CharacterSpellSlot.character_id == character_id,
                CharacterSpellSlot.spell_level == level,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_spell_slots(self, character_id: int) -> list[CharacterSpellSlot]:
        """List all of a character's spell slot entries."""

        result = await self.db.execute(
            select(CharacterSpellSlot).where(CharacterSpellSlot.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def apply_spell_slot_progression(
        self, character_id: int, slots_by_level: dict[str, int], *, commit: bool = True
    ) -> list[CharacterSpellSlot]:
        """
        Sync a character's actual ``CharacterSpellSlot.total`` values to
        match ``slots_by_level`` (as returned by
        ``ClassRepository.get_spell_slot_progression`` for the character's
        current class/level).

        For each level in ``slots_by_level``: upsert the slot row, setting
        ``total`` to the given value. The legacy ``used`` column is left
        untouched unless it would exceed the new ``total``, in which case
        it's clamped down to ``total`` (so the ``used <= total`` DB
        invariant always holds).

        For any level the character currently has a row for but that is
        *not* present in ``slots_by_level`` (e.g. leveling down, or
        switching to a class that doesn't grant that level): the row's
        ``total`` is set to 0 and ``used`` clamped to 0 with it, rather
        than deleted — this keeps history/ordering stable ("0 total =
        no slots").

        Levels never granted and not currently present in the character's
        rows are left alone (no zero-row is created for them).

        ``commit=False`` flushes instead, leaving the transaction open —
        ``CharacterService.create_character`` uses this so the character
        row and its initial slot rows commit (or roll back) together.
        """

        existing = {slot.spell_level: slot for slot in await self.get_all_spell_slots(character_id)}

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

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

        return await self.get_all_spell_slots(character_id)

    async def reset_all_spell_slots(self, character_id: int) -> None:
        """Set used=0 for every spell slot entry of the character (long rest)."""

        await self.db.execute(
            update(CharacterSpellSlot)
            .where(CharacterSpellSlot.character_id == character_id)
            .values({CharacterSpellSlot.used: 0})
        )
        await self.db.commit()


class CharacterSpellRepository(BaseRepository[CharacterSpell]):
    """
    Repository for a character's known spells (``character_spells``).

    Split out of the old single ``CharacterSpellRepository`` — this
    class owns only the known-spell rows. Spell slot totals live in
    the sibling ``CharacterSpellSlotRepository``.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterSpell, db)

    @staticmethod
    def _spell_load_options() -> list:
        """
        Eager-load the ``Spell`` plus its ``available_*`` relationships.

        ``CharacterSpellResponse.spell`` is the full ``SpellResponse``, which
        serializes ``available_classes``/``available_subclasses``/
        ``available_races``/``available_subraces``. Those ``Spell``
        relationships default to lazy loading, so without eager-loading them
        here the async session would raise ``MissingGreenlet`` during
        Pydantic serialization. Each sibling is its own ``Load`` path rooted
        at ``CharacterSpell.spell``.
        """
        base = selectinload(CharacterSpell.spell)
        return [
            base,
            base.selectinload(Spell.available_classes),
            base.selectinload(Spell.available_subclasses),
            base.selectinload(Spell.available_races),
            base.selectinload(Spell.available_subraces),
        ]

    async def get_known_spells(self, character_id: int) -> list[CharacterSpell]:
        """List all spells known by the character, each with its ``Spell`` eager-loaded."""

        result = await self.db.execute(
            select(CharacterSpell)
            .options(*self._spell_load_options())
            .where(CharacterSpell.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell | None:
        """Fetch a single known-spell entry, or None if not present."""
        result = await self.db.execute(
            select(CharacterSpell).where(
                CharacterSpell.character_id == character_id,
                CharacterSpell.spell_id == spell_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell:
        """Add a spell to the character's known spells."""

        character_spell = CharacterSpell(character_id=character_id, spell_id=spell_id)
        self.db.add(character_spell)
        await self.db.commit()

        result = await self.db.execute(
            select(CharacterSpell)
            .options(*self._spell_load_options())
            .where(
                CharacterSpell.character_id == character_id,
                CharacterSpell.spell_id == spell_id,
            )
        )
        return result.scalar_one()

    async def remove_known_spell(self, character_spell: CharacterSpell) -> bool:
        """Remove a spell from the character's known spells."""

        await self.db.delete(character_spell)
        await self.db.commit()
        return True

    async def count_known_spells_at_level(self, character_id: int, level: str) -> int:
        """
        Count how many spells the character already knows at a given
        ``Spell.level`` — compared against ``CharacterSpellSlot.total``
        for that level to cap how many spells of that level can be known
        at once. See ``CharacterSpellEligibilityChecker``.
        """

        result = await self.db.execute(
            select(func.count())
            .select_from(CharacterSpell)
            .join(Spell, Spell.id == CharacterSpell.spell_id)
            .where(
                CharacterSpell.character_id == character_id,
                Spell.level == level,
            )
        )
        return result.scalar_one()
