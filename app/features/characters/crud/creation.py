"""Character creation: reference validation, rule checks and the starting-state writes."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    BACKSTORY_MAX_LENGTH,
    FeatureSourceType,
    ProficiencyAction,
    ProficiencySourceType,
    ProficiencyType,
)
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.characters.ability_score.calculator import DEFAULT_SPEED
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.crud.exceptions import (
    ItemChoicesWithoutGroupsException,
    SuggestionIdsWithoutBackgroundException,
)
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.crud.rules import (
    pick_item_options,
    resolve_background_suggestions,
    starting_max_hp,
    validate_chosen_skills,
)
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.level.repository import CharacterMaxLevelRepository
from app.features.characters.proficiencies.writer import add_skill_proficiencies
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.schemas import CharacterCreate
from app.features.characters.spells.repository import CharacterSpellSlotRepository
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.items.crud.repository import ItemRepository
from app.features.races.crud.repository import RaceRepository
from app.features.races.exceptions import RaceNotFoundException, SubraceNotFoundException
from app.models import CharacterAbilityScore
from app.models.character.character_backstory_model import CharacterBackstory
from app.models.character.character_item_model import CharacterItem
from app.models.character.character_model import Character
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.items.item_source_choice_model import SourceItemChoiceOption

_EMPTY_PERSONALITY = {"personality_traits": "", "ideals": "", "bonds": "", "flaws": ""}


@dataclass
class CreationPlan:
    """Everything validated and resolved for one creation, ready to be written in a single transaction."""

    payload: dict[str, Any]
    character_class: Any
    chosen_skill_ids: list[int]
    background_skill_ids: list[int] = field(default_factory=list)
    race_skill_ids: list[int] = field(default_factory=list)
    item_options: list[SourceItemChoiceOption] = field(default_factory=list)
    backstory: str = ""


class CharacterCreationService:
    """
    The creation use case split in two steps: :meth:`prepare` validates every
    reference and choice (read-only), :meth:`persist` writes the character
    and its starting state with ``commit=False`` — the caller wraps it in the
    transaction and owns the commit.
    """

    def __init__(self, db: AsyncSession, stats_service: CharacterStatsService):
        """Wire up the collaborators."""

        self.db = db
        self.repository = CharacterRepository(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.item_repository = ItemRepository(db)
        self.max_level_repository = CharacterMaxLevelRepository(db)
        self.spell_slot_repository = CharacterSpellSlotRepository(db)
        self.stats_service = stats_service

    async def prepare(self, data: CharacterCreate, owner_id: int) -> CreationPlan:
        """
        Validate the references (class required; subclass/race/subrace/
        background must exist and belong together), the skill choices against
        the class, the background's suggestions and the equipment choices.
        """

        character_class = await self.class_repository.get_by_id(data.class_id)
        if character_class is None:
            raise ClassNotFoundException(class_id=data.class_id)

        if (
            data.subclass_id is not None
            and await self.class_repository.get_subclass(data.class_id, data.subclass_id) is None
        ):
            raise SubclassNotFoundException(class_id=data.class_id, subclass_id=data.subclass_id)

        race = await self._load_race(data)
        background = await self._load_background(data)

        chosen_skill_ids = validate_chosen_skills(data.skill_ids, character_class)
        item_options = await self._resolve_item_choices(data.class_id, data.background_id, data.item_choice_ids)

        if data.background_id is None and data.suggestion_ids:
            raise SuggestionIdsWithoutBackgroundException()

        payload = data.model_dump(exclude={"skill_ids", "item_choice_ids", "suggestion_ids"})
        payload.update(
            owner_id=owner_id,
            level=1,
            temp_hp=0,
            speed=race.speed if race is not None else DEFAULT_SPEED,
        )

        plan = CreationPlan(
            payload=payload,
            character_class=character_class,
            chosen_skill_ids=chosen_skill_ids,
            race_skill_ids=[skill.id for skill in race.granted_skills] if race is not None else [],
            item_options=item_options,
        )

        if background is not None:
            payload.update(resolve_background_suggestions(background, data.suggestion_ids))
            plan.background_skill_ids = [skill.id for skill in background.granted_skills]
            plan.backstory = (background.description or "")[:BACKSTORY_MAX_LENGTH]

        return plan

    async def persist(self, plan: CreationPlan) -> tuple[Character, CharacterAbilityScore]:
        """
        Write the character row, its max-level cap, proficiencies, spell
        slots, feature grants (effects are computed on read, only the
        grants are stored), ability-score cache row, starting HP,
        backstory and starting items. Never commits.

        Features are granted BEFORE the starting-HP math so their fixed
        ability effects (e.g. +4 CON) count in the first hit point; the
        session runs with ``autoflush=False``, hence the explicit flushes.
        """

        character = await self.repository.create(plan.payload, commit=False)

        if plan.backstory:
            self.db.add(CharacterBackstory(character_id=character.id, content=plan.backstory))

        await self.max_level_repository.create_for_character(character.id, character.level, commit=False)

        self._add_proficiencies(character, plan)
        await self.db.flush()
        await self.apply_spell_slot_progression(character, commit=False)

        await sync_progression_features(self.db, character)
        await self.db.flush()

        ability_scores = await self.stats_service.refresh(character, commit=False)
        character.max_hp = starting_max_hp(plan.character_class.hit_dice, ability_scores.constitution_total)
        character.current_hp = character.max_hp

        await self._add_starting_equipment(character, plan.item_options)
        await self.db.flush()
        return character, ability_scores

    async def apply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
        """Sync ``CharacterSpellSlot`` totals to the class's slot progression for the character's level."""

        slots_by_level = (
            await self.class_repository.get_spell_slot_progression(character.class_id, character.level)
            if character.class_id is not None
            else {}
        )
        await self.spell_slot_repository.apply_spell_slot_progression(character.id, slots_by_level, commit=commit)

    async def _load_race(self, data: CharacterCreate):
        """Load the race (404 when missing) and validate the subrace belongs to it."""

        if data.subrace_id is not None and data.race_id is None:
            raise SubraceNotFoundException(race_id=0, subrace_id=data.subrace_id)

        race = None
        if data.race_id is not None:
            race = await self.race_repository.get_by_id(data.race_id)
            if race is None:
                raise RaceNotFoundException(race_id=data.race_id)

        if (
            data.subrace_id is not None
            and await self.race_repository.get_subrace(data.race_id, data.subrace_id) is None
        ):
            raise SubraceNotFoundException(race_id=data.race_id, subrace_id=data.subrace_id)

        return race

    async def _load_background(self, data: CharacterCreate):
        """Load the background (404 when missing), or ``None`` when none was chosen."""

        if data.background_id is None:
            return None

        background = await self.background_repository.get_by_id(data.background_id)
        if background is None:
            raise BackgroundNotFoundException(background_id=data.background_id)

        return background

    @staticmethod
    def _sources(class_id: int | None, background_id: int | None) -> list[tuple[FeatureSourceType, int]]:
        """The ``(source type, id)`` pairs that grant starting equipment."""

        sources = []
        if class_id is not None:
            sources.append((FeatureSourceType.CLASS, class_id))
        if background_id is not None:
            sources.append((FeatureSourceType.BACKGROUND, background_id))
        return sources

    async def _resolve_item_choices(
        self, class_id: int | None, background_id: int | None, item_choice_ids: list[int]
    ) -> list[SourceItemChoiceOption]:
        """Resolve the "pick N of M" starting-equipment answers against the class/background choice groups."""

        sources = self._sources(class_id, background_id)
        groups = await self.item_repository.get_choice_groups_for_sources(sources) if sources else []

        if not groups:
            if item_choice_ids:
                raise ItemChoicesWithoutGroupsException()
            return []

        return pick_item_options(groups, item_choice_ids)

    def _add_proficiencies(self, character: Character, plan: CreationPlan) -> None:
        """
        Add the starting proficiency rows: skills tagged with their actual
        source (not deduplicated across sources), plus the class's saving
        throws, armor and weapon grants. Not routed through the feature
        engine, so they are written here directly.
        """

        character_class = plan.character_class
        add_skill_proficiencies(self.db, character.id, plan.chosen_skill_ids, ProficiencySourceType.CLASS_CHOICE)
        add_skill_proficiencies(self.db, character.id, plan.background_skill_ids, ProficiencySourceType.BACKGROUND)
        add_skill_proficiencies(self.db, character.id, plan.race_skill_ids, ProficiencySourceType.RACE)

        class_grant = {
            "character_id": character.id,
            "source_type": ProficiencySourceType.CLASS,
            "action": ProficiencyAction.GRANT,
        }
        for throw in character_class.saving_throws:
            self.db.add(
                CharacterProficiency(
                    proficiency_type=ProficiencyType.SAVING_THROW, ability=throw.ability, **class_grant
                )
            )
        for armor in character_class.armor_proficiencies:
            self.db.add(
                CharacterProficiency(proficiency_type=ProficiencyType.ARMOR, armor_type=armor.armor_type, **class_grant)
            )
        for weapon in character_class.weapon_proficiencies:
            self.db.add(
                CharacterProficiency(
                    proficiency_type=ProficiencyType.WEAPON, weapon_category=weapon.weapon_category, **class_grant
                )
            )

    async def _add_starting_equipment(self, character: Character, chosen_options: list[SourceItemChoiceOption]) -> None:
        """One ``CharacterItem`` stack per item, quantities summed across the sources and the chosen options."""

        sources = self._sources(character.class_id, character.background_id)
        if not sources:
            return

        quantities: dict[int, int] = {}
        for entry in await self.item_repository.get_source_items_for_sources(sources):
            quantities[entry.item_id] = quantities.get(entry.item_id, 0) + entry.quantity
        for option in chosen_options:
            quantities[option.item_id] = quantities.get(option.item_id, 0) + option.quantity

        for item_id, quantity in quantities.items():
            self.db.add(CharacterItem(character_id=character.id, item_id=item_id, quantity=quantity))
