"""The point-rebuild: replace a character's build and recompute everything derived from it."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import GrantSource, ProficiencySourceType
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.crud.rules import validate_chosen_skills
from app.features.characters.crud.service import CharacterService
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.proficiencies.writer import add_skill_proficiencies, delete_skill_proficiencies
from app.features.characters.progression.asi import AsiChoiceService
from app.features.characters.progression.exceptions import InvalidRebuildMaxHpException
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.rules import constitution_modifier, hit_die_sides, max_hp_bounds
from app.features.characters.progression.schemas import ASIChoice, CharacterRebuildRequest
from app.features.characters.spells.repository import CharacterSpellRepository
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.races.crud.repository import RaceRepository
from app.features.races.exceptions import RaceNotFoundException, SubraceNotFoundException
from app.models import Class
from app.models.character.character_model import Character

_REBUILT_SKILL_SOURCES = [
    ProficiencySourceType.CLASS_CHOICE,
    ProficiencySourceType.RACE,
    ProficiencySourceType.BACKGROUND,
]


@dataclass
class RebuildPlan:
    """A validated rebuild request, with the reference rows it resolved."""

    character_class: Class
    chosen_skill_ids: list[int]
    background_skill_ids: list[int]
    race_skill_ids: list[int]


class CharacterRebuilder:
    """
    Point-rebuild: replace the character's class/subclass/race/subrace/
    background and base ability scores, re-validate and re-apply the class
    skill choices, then recompute everything that derives from them in the
    caller's transaction:

    - Skill proficiencies are reconciled source-aware: only the CLASS_CHOICE/
      RACE/BACKGROUND rows are wiped and rebuilt; rows owned by the feature
      engine and GM overrides are untouched.
    - Source-owned features are reconciled to the new build via
      ``sync_progression_features``.
    - Every ASI level at or below the character's level is re-resolved from
      ``data.asi_choices``: the prior ASI-sourced feat grants and the
      level-resolved part of ``character_asi_choices`` are cleared first,
      then the new choices are applied in level order (so ability-cap checks
      see each choice's own predecessors, as when leveling up). GM
      adjustments and GM-granted feats are not part of that history and are
      kept. A feat's choice groups beyond its ASI pick stay pending (the
      payload has no place to answer them): they show up in
      ``GET /grants/pending``.
    - ``max_hp`` is the caller-supplied value, validated against the range
      the new class's hit die, the new effective CON modifier and the level
      allow (``rules.max_hp_bounds``); ``current_hp``/``temp_hp`` follow a
      level-up-style full heal.
    - Spell slots are re-applied for the new class/level and every known
      spell is cleared.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        asi: AsiChoiceService,
        stats_service: CharacterStatsService,
        character_service: CharacterService,
    ):
        """Wire the reference repositories and the collaborators shared with the progression service."""

        self.db = db
        self.asi = asi
        self.stats_service = stats_service
        self.character_service = character_service
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.character_spell_repository = CharacterSpellRepository(db)

    async def prepare(self, data: CharacterRebuildRequest) -> RebuildPlan:
        """Validate every reference and the skill choices of ``data``; the character's level is not needed yet."""

        character_class = await self.class_repository.get_by_id(data.class_id)
        if character_class is None:
            raise ClassNotFoundException(class_id=data.class_id)

        if (
            data.subclass_id is not None
            and await self.class_repository.get_subclass(data.class_id, data.subclass_id) is None
        ):
            raise SubclassNotFoundException(class_id=data.class_id, subclass_id=data.subclass_id)

        race = await self.race_repository.get_by_id(data.race_id)
        if race is None:
            raise RaceNotFoundException(race_id=data.race_id)

        if (
            data.subrace_id is not None
            and await self.race_repository.get_subrace(data.race_id, data.subrace_id) is None
        ):
            raise SubraceNotFoundException(race_id=data.race_id, subrace_id=data.subrace_id)

        background_skill_ids: list[int] = []
        if data.background_id is not None:
            background = await self.background_repository.get_by_id(data.background_id)
            if background is None:
                raise BackgroundNotFoundException(background_id=data.background_id)
            background_skill_ids = [skill.id for skill in background.granted_skills]

        return RebuildPlan(
            character_class=character_class,
            chosen_skill_ids=validate_chosen_skills(data.skill_ids, character_class),
            background_skill_ids=background_skill_ids,
            race_skill_ids=[skill.id for skill in race.granted_skills],
        )

    async def apply(self, character: Character, data: CharacterRebuildRequest, plan: RebuildPlan) -> dict[str, int]:
        """
        Apply the rebuild to the (locked) character and return its effective
        ability totals afterwards, ready to be stored in the stats cache.
        """

        character.class_id = data.class_id
        character.subclass_id = data.subclass_id
        character.race_id = data.race_id
        character.subrace_id = data.subrace_id
        character.background_id = data.background_id
        character.strength = data.strength
        character.dexterity = data.dexterity
        character.constitution = data.constitution
        character.intelligence = data.intelligence
        character.wisdom = data.wisdom
        character.charisma = data.charisma

        await sync_progression_features(self.db, character)
        await self._rebuild_skill_proficiencies(character, plan)
        await self.character_service.reapply_spell_slot_progression(character)
        await self.character_spell_repository.clear_known_spells(character.id)

        totals = await self._reapply_asi_history(character, data)

        minimum_hp, maximum_hp = max_hp_bounds(
            hit_die_sides(plan.character_class.hit_dice), constitution_modifier(totals), character.level
        )
        if not minimum_hp <= data.max_hp <= maximum_hp:
            raise InvalidRebuildMaxHpException(minimum=minimum_hp, maximum=maximum_hp)

        character.max_hp = data.max_hp
        character.current_hp = data.max_hp
        character.temp_hp = 0

        return totals

    async def _rebuild_skill_proficiencies(self, character: Character, plan: RebuildPlan) -> None:
        """
        Wipe ONLY the character's CLASS_CHOICE/RACE/BACKGROUND skill rows and
        rebuild them from the new choices/sources, each tagged with its
        actual source.
        """

        await delete_skill_proficiencies(self.db, character.id, _REBUILT_SKILL_SOURCES)

        add_skill_proficiencies(self.db, character.id, plan.chosen_skill_ids, ProficiencySourceType.CLASS_CHOICE)
        add_skill_proficiencies(self.db, character.id, plan.background_skill_ids, ProficiencySourceType.BACKGROUND)
        add_skill_proficiencies(self.db, character.id, plan.race_skill_ids, ProficiencySourceType.RACE)

        await self.db.flush()

    async def _reapply_asi_history(self, character: Character, data: CharacterRebuildRequest) -> dict[str, int]:
        """
        Replace the level-resolved ASI history with ``data.asi_choices``
        applied in level order; returns the effective totals afterwards.
        The totals are computed once and advanced in memory across ASI
        choices; a feat's own effects are only known after its grant, so
        totals are re-read after each feat.
        """

        await self.asi.feat_grant_repository.remove_feats_by_source(character.id, GrantSource.ASI)
        await self.asi.asi_repository.clear_character_choices(character.id)

        totals = await self.stats_service.compute(character)
        for asi_choice in sorted(data.asi_choices, key=lambda item: item.class_level):
            if isinstance(asi_choice.choice, ASIChoice):
                await self.asi.apply_asi(character, asi_choice.choice.increases, asi_choice.class_level, totals)
            else:
                await self.asi.apply_feat(
                    character, asi_choice.choice, asi_choice.class_level, totals, require_asi_pick=True
                )
                totals = await self.stats_service.compute(character)

        return totals
