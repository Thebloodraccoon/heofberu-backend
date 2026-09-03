"""Service for character progression: subclass/subrace/background setup, leveling up, rebuild stub."""

from sqlalchemy import select
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
    CharacterRebuildNotImplementedException,
    InvalidHitPointGainException,
    LevelUpChoiceNotAllowedException,
    LevelUpChoiceRequiredException,
)
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.characters.progression.schemas import (
    ASIIncreaseItem,
    BackgroundChange,
    CanLevelUpResponse,
    CharacterASIChoiceResponse,
    FeatChoice,
    LevelUpRequest,
    SubclassChange,
    SubraceChange,
)
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import SubclassNotFoundException
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.features.items.crud.repository import ItemRepository
from app.features.races.crud.repository import RaceRepository
from app.features.races.exceptions import SubraceNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_association_models import CharacterSkillProficiency
from app.models.character_item_model import CharacterItem
from app.models.character_model import Character


class CharacterProgressionService(CharacterSubDomainService):
    """
    Character progression: subclass/subrace change, late background setup,
    leveling up, and the (stubbed) full rebuild. Class and race are fixed
    once chosen; empty subclass/subrace/background slots can still be
    filled later.

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
        possible through the future rebuild endpoint.
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

    async def request_rebuild(self, character_id: int, current_user: UserResponse) -> None:
        """
        Point-rebuild placeholder: a full class/race swap is planned as a
        single rebuild operation that resets derived choices while keeping
        the character row; until implemented this raises 501.
        """

        character = await self.get_character_for_user(character_id, current_user)
        raise CharacterRebuildNotImplementedException(character_id=character.id)

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
