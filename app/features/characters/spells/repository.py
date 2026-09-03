"""Character spell repositories: spell slots and known spells."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.character_association_models import CharacterSpellSlot
from app.models.character_spell_model import CharacterSpell
from app.models.spell_model import Spell


class CharacterSpellSlotRepository(BaseRepository[CharacterSpellSlot]):
    """Repository for a character's spell slot totals per level (``character_spell_slots``)."""

    def __init__(self, db: AsyncSession):
        """Create the spell-slot repository."""

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
        Sync the character's ``total`` per level to ``slots_by_level``
        (from the class/level spell-slot progression): upsert each row,
        clamp ``used`` down to the new ``total`` if needed, and zero rows
        for levels the character no longer has (rather than delete them,
        keeping history stable — "0 total = no slots").
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
            await self.commit_or_flush()
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
        await self.commit_or_flush()


class CharacterSpellRepository(BaseRepository[CharacterSpell]):
    """Repository for a character's known spells (``character_spells``)."""

    def __init__(self, db: AsyncSession):
        """Create the known-spell repository."""

        super().__init__(CharacterSpell, db)

    @staticmethod
    def _spell_load_options() -> list:
        """
        Eager-load ``Spell`` plus its ``available_*`` relationships.
        ``CharacterSpellResponse.spell`` serializes those relationships,
        which default to lazy loading and would raise ``MissingGreenlet``
        under the async session if not loaded here.
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
        await self.commit_or_flush()

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
        await self.commit_or_flush()
        return True

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
