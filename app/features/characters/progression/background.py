"""Granting a background's skills and starting equipment to an existing character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType, ProficiencySourceType
from app.features.characters.items.repository import CharacterItemRepository
from app.features.characters.proficiencies.writer import add_skill_proficiencies
from app.features.characters.progression.exceptions import BackgroundItemChoicesNotSupportedException
from app.features.items.crud.repository import ItemRepository
from app.models.character.character_item_model import CharacterItem
from app.models.character.character_model import Character


class BackgroundGrants:
    """What setting a background after creation hands the character besides its features."""

    def __init__(self, db: AsyncSession):
        """Create the helper over the request's session."""

        self.db = db
        self.item_repository = ItemRepository(db)
        self.character_item_repository = CharacterItemRepository(db)

    async def ensure_no_item_choices(self, background_id: int) -> None:
        """
        The late-background path has no "pick N of M" surface: a background
        whose equipment is built on choice groups is rejected up front
        instead of silently dropping its options.
        """

        groups = await self.item_repository.get_choice_groups_for_sources(
            [(FeatureSourceType.BACKGROUND, background_id)]
        )
        if groups:
            raise BackgroundItemChoicesNotSupportedException(background_id=background_id)

    async def grant_skills(self, character: Character, skill_ids: list[int]) -> None:
        """Add the background's skills as BACKGROUND-sourced proficiency rows."""

        add_skill_proficiencies(self.db, character.id, skill_ids, ProficiencySourceType.BACKGROUND)
        await self.db.flush()

    async def grant_equipment(self, character: Character) -> None:
        """
        Grant the background's starting equipment, merging quantities into
        stacks the character already holds (same aggregation rule as
        character creation).
        """

        if character.background_id is None:
            return

        entries = await self.item_repository.get_source_items_for_sources(
            [(FeatureSourceType.BACKGROUND, character.background_id)]
        )
        if not entries:
            return

        quantities: dict[int, int] = {}
        for entry in entries:
            quantities[entry.item_id] = quantities.get(entry.item_id, 0) + entry.quantity

        stacks = await self.character_item_repository.get_stacks_by_item_ids(character.id, quantities)
        existing_items = {row.item_id: row for row in stacks}

        for item_id, quantity in quantities.items():
            stack = existing_items.get(item_id)
            if stack is not None:
                stack.quantity += quantity
            else:
                self.db.add(CharacterItem(character_id=character.id, item_id=item_id, quantity=quantity))

        await self.db.flush()
