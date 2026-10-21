"""Queries behind the choice-pick rules (``skill_rules`` / ``spell_rules``): catalog and character facts."""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import select

from app.core.base.repository import SessionRepository
from app.features.characters.grants.spell_rules import SpellFacts
from app.models.character.character_spell_model import CharacterGrantedSpell, CharacterSpell, CharacterSpellSlot
from app.models.skill_model import Skill
from app.models.spells.spell_association_models import spell_classes
from app.models.spells.spell_model import Spell


class GrantRulesRepository(SessionRepository):
    """Read-only lookups the pick rules judge against; the rules themselves stay pure."""

    async def all_skill_ids(self) -> list[int]:
        """Every skill id, ordered — the candidates for an open ("any skill") option."""

        return list((await self.db.execute(select(Skill.id).order_by(Skill.id))).scalars().all())

    async def missing_skill_ids(self, skill_ids: set[int]) -> list[int]:
        """The subset of ``skill_ids`` that match no skill."""

        if not skill_ids:
            return []

        found = set((await self.db.execute(select(Skill.id).where(Skill.id.in_(skill_ids)))).scalars().all())
        return sorted(skill_ids - found)

    async def spell_facts(self, spell_ids: Iterable[int] | None = None) -> dict[int, SpellFacts]:
        """``{spell_id: SpellFacts}`` for the given spells (every catalog spell when ``None``) — two plain queries."""

        spells = select(Spell.id, Spell.name, Spell.level, Spell.school, Spell.is_ritual)
        classes = select(spell_classes.c.spell_id, spell_classes.c.class_id)
        if spell_ids is not None:
            ids = set(spell_ids)
            if not ids:
                return {}
            spells = spells.where(Spell.id.in_(ids))
            classes = classes.where(spell_classes.c.spell_id.in_(ids))

        class_ids: dict[int, set[int]] = defaultdict(set)
        for spell_id, class_id in (await self.db.execute(classes)).all():
            class_ids[spell_id].add(class_id)

        return {
            spell_id: SpellFacts(
                id=spell_id,
                name=name,
                level=level,
                school=school,
                is_ritual=is_ritual,
                class_ids=frozenset(class_ids[spell_id]),
            )
            for spell_id, name, level, school, is_ritual in (await self.db.execute(spells)).all()
        }

    async def castable_spell_levels(self, character_id: int) -> set:
        """The spell levels the character has at least one slot of."""

        result = await self.db.execute(
            select(CharacterSpellSlot.spell_level).where(
                CharacterSpellSlot.character_id == character_id, CharacterSpellSlot.total > 0
            )
        )
        return set(result.scalars().all())

    async def row_spell_ids(self, character_id: int) -> set[int]:
        """The character's known spells and the GM's direct spell grants."""

        known = await self.db.execute(
            select(CharacterSpell.spell_id).where(CharacterSpell.character_id == character_id)
        )
        gm_granted = await self.db.execute(
            select(CharacterGrantedSpell.spell_id).where(CharacterGrantedSpell.character_id == character_id)
        )
        return {*known.scalars().all(), *gm_granted.scalars().all()}
