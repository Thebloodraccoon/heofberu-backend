"""Service for character progression: subclass/subrace/background setup, leveling up, point-rebuild."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ABILITY_SCORE_CAP, ASI_LEVELS, ASILevelChoice, CharacterFeatSource, FeatureSourceType
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.crud.service import CharacterService
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.feats.exceptions import CharacterFeatAlreadyKnownException
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.validation import (
    check_feat_prerequisite,
    validate_ability_score_increase,
)
from app.features.characters.level.repository import CharacterMaxLevelRepository
from app.features.characters.progression.exceptions import (
    AbilityScoreCapExceededException,
    BackgroundAlreadySetException,
    BackgroundItemChoicesNotSupportedException,
    CharacterAlreadyAtMaxLevelException,
    InvalidHitPointGainException,
    InvalidRebuildMaxHpException,
    LevelUpChoiceNotAllowedException,
    LevelUpChoiceRequiredException,
    RebuildAsiChoicesMismatchException,
)
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.characters.progression.schemas import (
    ASIIncreaseItem,
    BackgroundChange,
    CanLevelUpResponse,
    CharacterASIChoiceResponse,
    CharacterRebuildRequest,
    FeatChoice,
    LevelUpRequest,
    RebuildASIChoice,
    SubclassChange,
    SubraceChange,
)
from app.features.characters.spells.repository import CharacterSpellRepository
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.features.items.crud.repository import ItemRepository
from app.features.races.crud.repository import RaceRepository
from app.features.races.exceptions import RaceNotFoundException, SubraceNotFoundException
from app.features.users.schemas import UserResponse
from app.models import Class
from app.models.character_association_models import CharacterSkillProficiency
from app.models.character_item_model import CharacterItem
from app.models.character_model import Character


class CharacterProgressionService(CharacterSubDomainService):
    """
    Character progression: subclass/subrace change, late background setup,
    leveling up, and the full point-rebuild. Outside of a rebuild, class
    and race are fixed once chosen; empty subclass/subrace/background slots
    can still be filled later.

    Leveling up is the entry point for ability improvements: an ASI level
    (see ``ASI_LEVELS``) *requires* the request's ``choice``; the resolved
    ASI-or-feat is recorded in ``character_asi_choices``, the counted
    source of the points (the base columns stay untouched) and the audit
    trail that makes a future level-down a plain row deletion. Source-owned
    feature grants are reconciled automatically against the class, subclass,
    race/subrace, background, and feat grants; writes are transactional
    (one commit via :meth:`_atomic`, rolled back on validation failure).
    """

    def __init__(self, db: AsyncSession):
        """Create the progression service and its collaborators."""

        super().__init__(db)
        self.character_service = CharacterService(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.item_repository = ItemRepository(db)
        self.feat_repository = FeatRepository(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.asi_repository = CharacterASIChoiceRepository(db)
        self.max_level_repository = CharacterMaxLevelRepository(db)
        self.stats_service = CharacterStatsService(db)
        self.character_spell_repository = CharacterSpellRepository(db)

    async def set_subclass(self, character_id: int, data: SubclassChange, current_user: UserResponse) -> None:
        """
        Set or clear a character's subclass: ``subclass_id`` must reference
        a subclass of the current class, setting grants its features at or
        below the current level, clearing revokes them. Cache + stats
        refreshed because granted features can carry fixed ability effects.
        """

        character = await self.get_character_for_user(character_id, current_user)

        if (
            data.subclass_id is not None
            and await self.class_repository.get_subclass(character.class_id, data.subclass_id) is None
        ):
            raise SubclassNotFoundException(class_id=character.class_id, subclass_id=data.subclass_id)

        async with self._atomic():
            character.subclass_id = data.subclass_id
            await sync_progression_features(self.repository.db, character)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

    async def set_subrace(self, character_id: int, data: SubraceChange, current_user: UserResponse) -> None:
        """
        Set or clear a character's subrace: ``subrace_id`` must reference a
        subrace of the current race (the character must have a race). Setting
        grants its features at or below the current level, clearing revokes
        them. The ability-score cache is refreshed to re-derive bonuses.
        """

        character = await self.get_character_for_user(character_id, current_user)

        if data.subrace_id is not None:
            if character.race_id is None:
                raise SubraceNotFoundException(race_id=0, subrace_id=data.subrace_id)
            if await self.race_repository.get_subrace(character.race_id, data.subrace_id) is None:
                raise SubraceNotFoundException(race_id=character.race_id, subrace_id=data.subrace_id)

        async with self._atomic():
            character.subrace_id = data.subrace_id
            await sync_progression_features(self.repository.db, character)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

    async def set_background(self, character_id: int, data: BackgroundChange, current_user: UserResponse) -> None:
        """
        Set a character's background — only while it has none. In one
        transaction it grants the background's features
        (``sync_progression_features``), its skills (deduped against current
        proficiencies), and its starting equipment (merged into stacks). A
        background whose equipment is built on "pick N of M" choice groups
        is rejected up front (no late-choice surface). Re-choosing is only
        possible through :meth:`rebuild_character`.
        """

        character = await self.get_character_for_user(character_id, current_user)

        if character.background_id is not None:
            raise BackgroundAlreadySetException(character_id=character.id, background_id=character.background_id)

        background = await self.background_repository.get_by_id(data.background_id)
        if background is None:
            raise BackgroundNotFoundException(background_id=data.background_id)

        # The late-background path has no "pick N of M" surface: a
        # background whose equipment is built on choice groups is rejected
        # up front instead of silently dropping its options.
        groups = await self.item_repository.get_choice_groups_for_sources(
            [(FeatureSourceType.BACKGROUND, background.id)]
        )
        if groups:
            raise BackgroundItemChoicesNotSupportedException(background_id=background.id)

        async with self._atomic():
            character.background_id = data.background_id

            await sync_progression_features(self.repository.db, character)
            await self._grant_background_skills(character, background.granted_skills)
            await self._grant_background_equipment(character)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

    async def rebuild_character(
        self, character_id: int, data: CharacterRebuildRequest, current_user: UserResponse
    ) -> None:
        """
        Point-rebuild: replace the character's class/subclass/race/subrace/
        background and base ability scores, re-validate and re-apply the
        class skill choices, then recompute everything that derives from
        them in one transaction:

        - Skill proficiencies are wiped and rebuilt from scratch (the
          validated new class choices plus the new background's/race's
          granted skills) — there is no per-row "source" to reconcile
          against, so expertise flags reset, same as a fresh character.
        - Source-owned features are reconciled to the new
          class/subclass/race/subrace/background via
          ``sync_progression_features``.
        - Every ASI level (see ``ASI_LEVELS``) at or below the character's
          current level is re-resolved from ``data.asi_choices`` (required,
          one per reached level): prior ASI-sourced feat grants and the
          entire ``character_asi_choices`` log are cleared first, then the
          new choices are applied in level order (so ability-cap checks
          see each choice's own predecessors, same as leveling up
          normally).
        - ``max_hp`` is the caller-supplied value, validated against the
          range the new class's hit die, its new effective CON modifier,
          and the character's level allow (see ``_max_hp_bounds``) — a
          rebuild has no remembered per-level roll history to recompute
          it from. ``current_hp``/``temp_hp`` follow a level-up-style
          full heal.
        - Spell slot totals are re-applied for the new class/level and
          every known spell is cleared (the old class's spells no longer
          apply, and the new class may not even cast).
        - The ability-score cache is refreshed.

        ``level``, notes, personality, backstory, inventory, and
        GM-granted feats are left untouched.
        """

        character = await self.get_character_for_user(character_id, current_user)

        character_class = await self._validate_rebuild_references(data)
        chosen_skill_ids = CharacterService._validate_chosen_skills(data.skill_ids, character_class)
        self._validate_rebuild_asi_choices(character.level, data.asi_choices)

        background_skill_ids: list[int] = []
        if data.background_id is not None:
            background = await self.background_repository.get_by_id(data.background_id)
            if background is not None:
                background_skill_ids = [skill.id for skill in background.granted_skills]

        race = await self.race_repository.get_by_id(data.race_id)
        race_skill_ids = [skill.id for skill in race.granted_skills] if race is not None else []

        async with self._atomic():
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

            # Features are reconciled BEFORE the ASI/HP math so fixed
            # ability effects (e.g. +4 CON) from newly granted features
            # are included in the effective CON modifier, mirroring
            # character creation.
            await sync_progression_features(self.repository.db, character)
            await self.repository.db.flush()

            await self._rebuild_skill_proficiencies(character, chosen_skill_ids, background_skill_ids, race_skill_ids)
            await self.character_service.reapply_spell_slot_progression(character, commit=False)
            await self.character_spell_repository.clear_known_spells(character.id, commit=False)

            # Replaces the ASI-level history: the old choices were resolved
            # against a build (class/ability scores) that no longer exists,
            # so they are cleared and re-applied fresh, in level order, so
            # each choice's ability-cap check sees its own predecessors.
            await self.feat_grant_repository.remove_feats_by_source(character.id, CharacterFeatSource.ASI, commit=False)
            await self.asi_repository.clear_character_choices(character.id, commit=False)
            for asi_choice in sorted(data.asi_choices, key=lambda item: item.class_level):
                if asi_choice.choice.type == ASILevelChoice.ASI:
                    await self._apply_asi(character, asi_choice.choice.increases, asi_choice.class_level)
                else:
                    await self._apply_feat(character, asi_choice.choice, asi_choice.class_level)

            minimum_hp, maximum_hp = await self._max_hp_bounds(character, character_class)
            if not (minimum_hp <= data.max_hp <= maximum_hp):
                raise InvalidRebuildMaxHpException(minimum=minimum_hp, maximum=maximum_hp)

            character.max_hp = data.max_hp
            character.current_hp = data.max_hp
            character.temp_hp = 0

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

    async def _validate_rebuild_references(self, data: CharacterRebuildRequest) -> Class:
        """
        Validate every FK on a rebuild payload (mirrors
        ``CharacterService._validate_references``, except ``race_id`` is
        required here, not optional) and return the resolved class row
        (eager-loaded ``available_skills``/``hit_dice``).
        """

        character_class = await self.class_repository.get_by_id(data.class_id)
        if character_class is None:
            raise ClassNotFoundException(class_id=data.class_id)

        if (
            data.subclass_id is not None
            and await self.class_repository.get_subclass(data.class_id, data.subclass_id) is None
        ):
            raise SubclassNotFoundException(class_id=data.class_id, subclass_id=data.subclass_id)

        if not await self.race_repository.exists_by_id(data.race_id):
            raise RaceNotFoundException(race_id=data.race_id)

        if (
            data.subrace_id is not None
            and await self.race_repository.get_subrace(data.race_id, data.subrace_id) is None
        ):
            raise SubraceNotFoundException(race_id=data.race_id, subrace_id=data.subrace_id)

        if data.background_id is not None and not await self.background_repository.exists_by_id(data.background_id):
            raise BackgroundNotFoundException(background_id=data.background_id)

        return character_class

    @staticmethod
    def _validate_rebuild_asi_choices(character_level: int, asi_choices: list[RebuildASIChoice]) -> None:
        """
        Require exactly one ``asi_choices`` entry per ASI level (see
        ``ASI_LEVELS``) at or below ``character_level`` — no fewer (an
        unresolved level), no more (a level the character hasn't reached).
        """

        required_levels = {level for level in ASI_LEVELS if level <= character_level}
        provided_levels = {item.class_level for item in asi_choices}

        if provided_levels != required_levels:
            raise RebuildAsiChoicesMismatchException(
                required_levels=sorted(required_levels), provided_levels=sorted(provided_levels)
            )

    async def _rebuild_skill_proficiencies(
        self,
        character: Character,
        chosen_skill_ids: list[int],
        background_skill_ids: list[int],
        race_skill_ids: list[int],
    ) -> None:
        """
        Wipe the character's skill proficiencies and rebuild them from the
        new choices/sources (merged and deduplicated, same as character
        creation), all starting with ``is_expertise=False``.
        """

        await self.repository.db.execute(
            delete(CharacterSkillProficiency).where(CharacterSkillProficiency.character_id == character.id)
        )

        merged_skill_ids = list(dict.fromkeys([*chosen_skill_ids, *background_skill_ids, *race_skill_ids]))
        for skill_id in merged_skill_ids:
            self.repository.db.add(
                CharacterSkillProficiency(character_id=character.id, skill_id=skill_id, is_expertise=False)
            )

        await self.repository.db.flush()

    async def _max_hp_bounds(self, character: Character, character_class: Class) -> tuple[int, int]:
        """
        The valid ``max_hp`` range for a rebuild, given the new class's
        hit die and the character's (post-rebuild) effective CON modifier
        across its current level: level 1 always grants the full hit die
        + CON modifier (never a range, per 5e's level-1 rule, floored at
        1); each level above it contributes between 1 and hit die + CON
        modifier (floored at 1) — the same bounds ``level_up`` enforces
        per level, applied here across every level at once since a
        rebuild has no per-level roll history to validate individually.
        """

        die_sides = int(character_class.hit_dice.value[1:])
        con_mod = await self._constitution_modifier(character)

        level_1_hp = max(die_sides + con_mod, 1)
        if character.level <= 1:
            return level_1_hp, level_1_hp

        max_gain = max(die_sides + con_mod, 1)
        levels_above_one = character.level - 1
        return level_1_hp + levels_above_one, level_1_hp + levels_above_one * max_gain

    async def _grant_background_skills(self, character: Character, granted_skills) -> None:
        """Add the background's granted skills as proficiency rows, skipping skills the character already has."""

        existing_result = await self.repository.db.execute(
            select(CharacterSkillProficiency.skill_id).where(CharacterSkillProficiency.character_id == character.id)
        )
        existing_ids = {skill_id for (skill_id,) in existing_result.all()}

        for skill in granted_skills:
            if skill.id not in existing_ids:
                self.repository.db.add(
                    CharacterSkillProficiency(
                        character_id=character.id,
                        skill_id=skill.id,
                        is_expertise=False,
                    )
                )

        await self.repository.db.flush()

    async def _grant_background_equipment(self, character: Character) -> None:
        """
        Grant the background's starting equipment, merging quantities into
        stacks the character already holds (same aggregation rule as
        character creation).
        """

        entries = await self.item_repository.get_source_items_for_sources(
            [(FeatureSourceType.BACKGROUND, character.background_id)]
        )
        if not entries:
            return

        quantities: dict[int, int] = {}
        for entry in entries:
            quantities[entry.item_id] = quantities.get(entry.item_id, 0) + entry.quantity

        existing_result = await self.repository.db.execute(
            select(CharacterItem).where(
                CharacterItem.character_id == character.id,
                CharacterItem.item_id.in_(quantities.keys()),
            )
        )
        existing_items = {row.item_id: row for row in existing_result.scalars().all()}

        for item_id, quantity in quantities.items():
            stack = existing_items.get(item_id)
            if stack is not None:
                stack.quantity += quantity
            else:
                self.repository.db.add(CharacterItem(character_id=character.id, item_id=item_id, quantity=quantity))

        await self.repository.db.flush()

    async def level_up(self, character_id: int, data: LevelUpRequest, current_user: UserResponse) -> None:
        """
        Advance a character exactly one level, only while below the
        GM-set maximum (``character_max_levels``). At an ASI level
        (4/8/12/16/19) a ``choice`` is required, at any other level it is
        rejected. HP defaults to the class's standard average (half hit
        die + 1 + CON) unless ``hit_points_gained`` is given (bounded by
        the hit die + CON). Features unlocked by the new level are granted
        and spell slots re-applied. Leveling up fully heals the character:
        ``current_hp`` is set to the new ``max_hp`` and ``temp_hp`` clears.
        """

        character = await self.get_character_for_user(character_id, current_user)

        max_level = await self._allowed_max_level(character_id, character.level)
        if character.level >= max_level:
            raise CharacterAlreadyAtMaxLevelException(character_id, max_level)

        new_level = character.level + 1
        is_asi_level = new_level in ASI_LEVELS

        if is_asi_level and data.choice is None:
            raise LevelUpChoiceRequiredException(class_level=new_level)

        if not is_asi_level and data.choice is not None:
            raise LevelUpChoiceNotAllowedException(class_level=new_level)

        async with self._atomic():
            character.level = new_level

            if data.choice is not None:
                if data.choice.type == ASILevelChoice.ASI:
                    await self._apply_asi(character, data.choice.increases, new_level)
                else:
                    await self._apply_feat(character, data.choice, new_level)

            hp_gain = await self._resolve_hp_gain(character, data.hit_points_gained)
            character.max_hp += hp_gain
            # A level-up fully heals: current HP is restored to the new
            # maximum and any temporary HP is cleared.
            character.current_hp = character.max_hp
            character.temp_hp = 0

            # Grant any class/subclass features unlocked by the new level.
            await sync_progression_features(self.repository.db, character)
            await self.character_service.reapply_spell_slot_progression(character, commit=False)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

    async def get_asi_choices(self, character_id: int, current_user: UserResponse) -> list[CharacterASIChoiceResponse]:
        """Return the character's resolved ASI-level choices, for audit."""

        await self.get_character_for_user(character_id, current_user)
        choices = await self.asi_repository.get_character_choices(character_id)

        return [CharacterASIChoiceResponse.model_validate(choice) for choice in choices]

    async def can_level_up(self, character_id: int, current_user: UserResponse) -> CanLevelUpResponse:
        """
        Report whether the character may take another level-up: it is
        possible while the character's level is below the GM-set maximum
        (``character_max_levels``).
        """

        character = await self.get_character_for_user(character_id, current_user)
        max_level = await self._allowed_max_level(character_id, character.level)

        return CanLevelUpResponse(
            can_level_up=character.level < max_level,
            current_level=character.level,
            max_level=max_level,
        )

    async def _allowed_max_level(self, character_id: int, character_level: int) -> int:
        """
        The maximum level the character may reach, from its
        ``character_max_levels`` row. A missing row is treated defensively
        as capped at the character's current level — characters always get
        a row at creation and via the migration backfill.
        """

        row = await self.max_level_repository.get_by_character_id(character_id)
        return row.max_level if row is not None else min(character_level, ABILITY_SCORE_CAP)

    async def _apply_asi(self, character: Character, increases: list[ASIIncreaseItem], class_level: int) -> None:
        """
        Apply an Ability Score Improvement: validate that no ability's
        *effective* total would exceed the standard ``ABILITY_SCORE_CAP``
        (20) — player level-up choices are always capped at 20 regardless
        of any feature ``new_cap`` that lets a score reach 30 via GM
        intervention — then record the choice. The base columns are NOT
        touched; increments live only in the ``character_asi_choices`` log
        and are counted from there, keeping the base columns easy to rebuild
        and a future level-down a plain row deletion.
        """

        totals = await self.stats_service.compute(character)
        for item in increases:
            total_field = TOTAL_FIELD_BY_ABILITY[item.ability]
            current_total = totals[total_field]

            if current_total + item.amount > ABILITY_SCORE_CAP:
                raise AbilityScoreCapExceededException(
                    ability=item.ability.value,
                    current_total=current_total,
                    requested=current_total + item.amount,
                )

        await self.asi_repository.add(
            character.id,
            class_level,
            ASILevelChoice.ASI,
            increases=[{"ability": item.ability.value, "amount": item.amount} for item in increases],
            commit=False,
        )

    async def _apply_feat(self, character: Character, choice: FeatChoice, class_level: int) -> None:
        """
        Apply a feat-as-ASI: validate the feat exists, isn't already
        known, has a valid ASI pick (if any) and the prerequisite is met,
        then grant it (source ``ASI``) and record the choice.
        """

        feat = await self.feat_repository.get_by_id(choice.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=choice.feat_id)

        existing = await self.feat_grant_repository.get_character_feat_by_feat_id(character.id, choice.feat_id)
        if existing:
            raise CharacterFeatAlreadyKnownException(character_id=character.id, feat_id=choice.feat_id)

        validate_ability_score_increase(feat, choice.ability_score_increase_id)
        await check_feat_prerequisite(character, feat, self.stats_service)

        await self.feat_grant_repository.add_character_feat(
            character.id,
            choice.feat_id,
            choice.ability_score_increase_id,
            source_type=CharacterFeatSource.ASI,
            commit=False,
        )
        await self.asi_repository.add(
            character.id,
            class_level,
            ASILevelChoice.FEAT,
            feat_id=choice.feat_id,
            ability_score_increase_id=choice.ability_score_increase_id,
            commit=False,
        )

    async def _resolve_hp_gain(self, character: Character, requested: int | None) -> int:
        """
        Default HP gain is half hit die + 1 + CON modifier (never less than
        1 — the 5e minimum of one HP per level); a provided value must fit
        the die + CON bounds, which are also clamped to at least 1.
        """

        die_sides = await self._class_die_sides(character)
        con_mod = await self._constitution_modifier(character)
        if requested is None:
            return max(1, die_sides // 2 + 1 + con_mod)

        max_gain = max(1, die_sides + con_mod)
        if requested < 1 or requested > max_gain:
            raise InvalidHitPointGainException(minimum=1, maximum=max_gain)

        return requested

    async def _class_die_sides(self, character: Character) -> int:
        """Hit die sides of the character's class (e.g. ``"D8"`` -> 8)."""

        character_class = await self.class_repository.get_by_id(character.class_id)
        if character_class is None:
            return 0

        return int(character_class.hit_dice.value[1:])

    async def _constitution_modifier(self, character: Character) -> int:
        """CON modifier from the character's current *effective* CON total."""

        totals = await self.stats_service.compute(character)
        return (totals["constitution_total"] - 10) // 2
