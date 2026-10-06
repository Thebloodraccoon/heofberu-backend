"""Character spell repositories: spell slots and known spells, plus a granted-spell repository."""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository, SessionRepository
from app.models.character.character_spell_model import CharacterGrantedSpell, CharacterSpell, CharacterSpellSlot
from app.models.spells.spell_model import Spell


class CharacterSpellSlotRepository(SessionRepository):
    """Repository for a character's spell slot totals per level (``character_spell_slots``)."""

    def __init__(self, db: AsyncSession):
        """Create the spell-slot repository."""

        super().__init__(db)

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
        self, character_id: int, slots_by_level: dict[str, int]
    ) -> list[CharacterSpellSlot]:
        """
        Sync the character's ``total`` per level to ``slots_by_level``
        (from the class/level spell-slot progression): upsert each row and
        zero rows for levels the character no longer has (rather than delete
        them, keeping history stable — "0 total = no slots").
        """

        existing: dict[str, CharacterSpellSlot] = {
            slot.spell_level: slot for slot in await self.get_all_spell_slots(character_id)
        }

        for level, total in slots_by_level.items():
            slot = existing.get(level)
            if slot is None:
                self.db.add(CharacterSpellSlot(character_id=character_id, spell_level=level, total=total))
            else:
                slot.total = total

        for level, slot in existing.items():
            if level not in slots_by_level:
                slot.total = 0

        await self.flush()

        return await self.get_all_spell_slots(character_id)

    async def reset_all_spell_slots(self, character_id: int) -> None:
        """Set used=0 for every spell slot entry of the character (long rest)."""

        await self.db.execute(
            update(CharacterSpellSlot)
            .where(CharacterSpellSlot.character_id == character_id)
            .values({CharacterSpellSlot.used: 0})
        )
        await self.flush()


class CharacterSpellRepository(SessionRepository):
    """Repository for a character's known spells (``character_spells``)."""

    def __init__(self, db: AsyncSession):
        """Create the known-spell repository."""

        super().__init__(db)

    @staticmethod
    def _spell_load_options() -> list:
        """Eager-load the ``Spell`` row (``CharacterSpellResponse`` needs no availability relationships)."""

        return [selectinload(CharacterSpell.spell)]

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
        """Add a spell to the character's known spells (flushed; the caller's atomic block commits)."""

        character_spell = CharacterSpell(character_id=character_id, spell_id=spell_id)
        self.db.add(character_spell)
        await self.db.flush()
        return character_spell

    async def remove_known_spell(self, character_spell: CharacterSpell) -> None:
        """Remove a spell from the character's known spells (flushed; the caller's atomic block commits)."""

        await self.db.delete(character_spell)
        await self.db.flush()

    async def clear_known_spells(self, character_id: int) -> None:
        """
        Delete every known-spell row for a character (e.g. a point-rebuild:
        the old class's spells no longer apply and the new class may not
        even cast).
        """

        await self.db.execute(delete(CharacterSpell).where(CharacterSpell.character_id == character_id))
        await self.flush()

    async def count_known_spells_at_level(self, character_id: int, level: str) -> int:
        """
        Count the spells the character already knows at ``level``, compared
        against the slot ``total`` for that level to cap known spells.
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


class CharacterGrantedSpellRepository(BaseRepository[CharacterGrantedSpell]):
    """Repository for spells the GM granted directly (``character_granted_spells``)."""

    def __init__(self, db: AsyncSession):
        """Create the granted-spell repository."""

        super().__init__(CharacterGrantedSpell, db)

    @staticmethod
    def _spell_load_options() -> list:
        """Eager-load the ``Spell`` row (``CharacterSpellResponse`` needs no availability relationships)."""

        return [selectinload(CharacterGrantedSpell.spell)]

    async def get_granted_spells(self, character_id: int) -> list[CharacterGrantedSpell]:
        """List every spell the GM granted the character directly, each with its ``Spell`` eager-loaded."""

        result = await self.db.execute(
            select(CharacterGrantedSpell)
            .options(*self._spell_load_options())
            .where(CharacterGrantedSpell.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_granted_spell(self, character_id: int, spell_id: int) -> CharacterGrantedSpell | None:
        """Fetch the character's GM-granted row for a spell (at most one — ``uq_character_granted_spell``)."""

        result = await self.db.execute(
            select(CharacterGrantedSpell).where(
                CharacterGrantedSpell.character_id == character_id,
                CharacterGrantedSpell.spell_id == spell_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_spell(self, spell_id: int) -> Spell | None:
        """Fetch a plain ``Spell`` row (no availability relationships), or ``None``."""

        return await self.db.get(Spell, spell_id)

    async def add_granted_spell(self, character_id: int, spell_id: int) -> CharacterGrantedSpell:
        """
        Grant a spell directly to a character (a free-form, GM-authored
        grant — no feature/feat behind it; only the GM removes it). Flushed;
        the caller's atomic block commits.
        """

        row = CharacterGrantedSpell(character_id=character_id, spell_id=spell_id)
        self.db.add(row)
        await self.db.flush()
        return row

    async def remove_granted_spell(self, row: CharacterGrantedSpell) -> None:
        """Remove a granted-spell row from a character (flushed; the caller's atomic block commits)."""

        await self.db.delete(row)
        await self.db.flush()
