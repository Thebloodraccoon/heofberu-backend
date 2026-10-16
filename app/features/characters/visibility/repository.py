"""Read queries of the public character card (column rows, never the full sheet)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.base.repository import SessionRepository
from app.models.character.character_ability_score_model import CharacterAbilityScore
from app.models.character.character_backstory_model import CharacterBackstory
from app.models.character.character_item_model import CharacterItem
from app.models.character.character_model import Character
from app.models.character.character_spell_model import CharacterSpell
from app.models.classes.class_model import Class
from app.models.classes.subclass_model import Subclass
from app.models.items.item_model import Item
from app.models.races.race_model import Race
from app.models.races.subrace_model import Subrace
from app.models.spells.spell_model import Spell
from app.models.user_model import User


def concept_columns() -> list[Any]:
    """Columns of ``PublicCharacterConcept`` (needs ``with_concept_joins``)."""

    return [
        Character.id,
        Character.name,
        Character.level,
        Class.name.label("class_name"),
        Subclass.name.label("subclass_name"),
        Race.name.label("race_name"),
        Subrace.name.label("subrace_name"),
        User.username.label("owner_username"),
        Character.public_visibility,
    ]


def with_concept_joins(stmt: Any) -> Any:
    """Join the class/subclass/race/subrace names and the owner's username ``concept_columns`` read."""

    return (
        stmt.join(Class, Class.id == Character.class_id)
        .join(User, User.id == Character.owner_id)
        .outerjoin(Subclass, Subclass.id == Character.subclass_id)
        .outerjoin(Race, Race.id == Character.race_id)
        .outerjoin(Subrace, Subrace.id == Character.subrace_id)
    )


class CharacterVisibilityRepository(SessionRepository):
    """The owner's visibility switch and the public card reads."""

    async def get_owner_and_visibility(self, character_id: int) -> Any:
        """``(owner_id, public_visibility)`` of the character, or ``None`` when it doesn't exist."""

        result = await self.db.execute(
            select(Character.owner_id, Character.public_visibility).where(Character.id == character_id)
        )
        return result.first()

    async def set_visibility(self, character_id: int, visibility: Any) -> None:
        """Write the new visibility (flush only)."""

        character = await self.db.get(Character, character_id)
        character.public_visibility = visibility
        await self.flush()

    async def get_card_row(self, character_id: int) -> Any:
        """Concept columns plus the personality fields, backstory and ability totals, in one row."""

        backstory = aliased(CharacterBackstory)
        stmt = with_concept_joins(
            select(
                *concept_columns(),
                Character.personality_traits,
                Character.ideals,
                Character.bonds,
                Character.flaws,
                backstory.content.label("backstory"),
                CharacterAbilityScore.strength_total,
                CharacterAbilityScore.dexterity_total,
                CharacterAbilityScore.constitution_total,
                CharacterAbilityScore.intelligence_total,
                CharacterAbilityScore.wisdom_total,
                CharacterAbilityScore.charisma_total,
            )
        )
        stmt = (
            stmt.outerjoin(backstory, backstory.character_id == Character.id)
            .outerjoin(CharacterAbilityScore, CharacterAbilityScore.character_id == Character.id)
            .where(Character.id == character_id)
        )
        return (await self.db.execute(stmt)).first()

    async def list_items(self, character_id: int) -> list[Any]:
        """``(name, quantity)`` of every inventory stack, by item name."""

        result = await self.db.execute(
            select(Item.name, CharacterItem.quantity)
            .join(Item, Item.id == CharacterItem.item_id)
            .where(CharacterItem.character_id == character_id)
            .order_by(Item.name)
        )
        return list(result.all())

    async def list_spell_names(self, character_id: int) -> list[str]:
        """Names of the character's known spells, alphabetically."""

        result = await self.db.scalars(
            select(Spell.name)
            .join(CharacterSpell, CharacterSpell.spell_id == Spell.id)
            .where(CharacterSpell.character_id == character_id)
            .order_by(Spell.name)
        )
        return list(result)
