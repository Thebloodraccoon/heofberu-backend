"""Service for character progression: subclass/subrace/background setup, leveling up, point-rebuild."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.crud.service import CharacterService
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.grants.schemas import ChoiceAnswerItem
from app.features.characters.grants.service import FeatureGrantService
from app.features.characters.level.repository import CharacterMaxLevelRepository
from app.features.characters.progression.asi import AsiChoiceService
from app.features.characters.progression.background import BackgroundGrants
from app.features.characters.progression.exceptions import (
    BackgroundAlreadySetException,
    CharacterAlreadyAtMaxLevelException,
)
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.rebuild import CharacterRebuilder
from app.features.characters.progression.rules import (
    check_level_up_choice,
    check_rebuild_asi_levels,
    constitution_modifier,
    default_max_level,
    hit_die_sides,
    resolve_hp_gain,
)
from app.features.characters.progression.schemas import (
    BackgroundChange,
    CanLevelUpResponse,
    CharacterASIChoiceResponse,
    CharacterRebuildRequest,
    LevelUpFeatureChoiceAnswer,
    LevelUpRequest,
    SubclassChange,
    SubraceChange,
)
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.races.crud.repository import RaceRepository
from app.features.races.exceptions import SubraceNotFoundException
from app.features.users.schemas import UserResponse
from app.models import Class
from app.models.character.character_model import Character


class CharacterProgressionService(CharacterSubDomainService):
    """
    Character progression: subclass/subrace change, late background setup,
    leveling up, and the full point-rebuild. Outside of a rebuild, class and
    race are fixed once chosen; empty subclass/subrace/background slots can
    still be filled later.

    Leveling up is the entry point for ability improvements: an ASI level
    (see ``ASI_LEVELS``) *requires* the request's ``choice``; the resolved
    ASI-or-feat is recorded in ``character_asi_choices``, the counted source
    of the points (the base columns stay untouched). Source-owned feature
    grants are reconciled automatically against the class, subclass,
    race/subrace and background; an ASI-level feat is granted through the
    same engine (``grant_source=ASI``).

    Every write is one use case with this service as the single transaction
    owner: the character row is locked first (a double submit cannot apply
    twice), the ability-score cache is refreshed in the same transaction and
    the Redis payload is purged only after the commit. The cohesive parts
    live in ``asi`` (ASI-level choices), ``background`` (late background
    grants), ``rebuild`` and ``rules`` (pure HP/ASI rules).
    """

    def __init__(self, db: AsyncSession):
        """Create the progression service and its collaborators."""

        super().__init__(db)
        self.db = db
        self.character_service = CharacterService(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.max_level_repository = CharacterMaxLevelRepository(db)
        self.stats_service = CharacterStatsService(db)
        self.grant_service = FeatureGrantService(db)
        self.asi = AsiChoiceService(db)
        self.background_grants = BackgroundGrants(db)
        self.rebuilder = CharacterRebuilder(
            db, asi=self.asi, stats_service=self.stats_service, character_service=self.character_service
        )

    async def set_subclass(self, character_id: int, data: SubclassChange, current_user: UserResponse) -> None:
        """
        Set or clear a character's subclass: ``subclass_id`` must reference a
        subclass of the current class, setting grants its features at or
        below the current level, clearing revokes them. The ability-score
        cache is refreshed because granted features can carry ability effects.
        """

        character = await self.get_character_for_user(character_id, current_user)

        async with self._unit_of_work():
            await self._lock_character(character)

            if (
                data.subclass_id is not None
                and await self.class_repository.get_subclass(character.class_id, data.subclass_id) is None
            ):
                raise SubclassNotFoundException(class_id=character.class_id, subclass_id=data.subclass_id)

            character.subclass_id = data.subclass_id
            await sync_progression_features(self.db, character)
            await self._finish(character)

    async def set_subrace(self, character_id: int, data: SubraceChange, current_user: UserResponse) -> None:
        """
        Set or clear a character's subrace: ``subrace_id`` must reference a
        subrace of the current race (the character must have a race). Setting
        grants its features at or below the current level, clearing revokes
        them. The ability-score cache is refreshed to re-derive bonuses.
        """

        character = await self.get_character_for_user(character_id, current_user)

        async with self._unit_of_work():
            await self._lock_character(character)

            if data.subrace_id is not None:
                if character.race_id is None:
                    raise SubraceNotFoundException(race_id=0, subrace_id=data.subrace_id)
                if await self.race_repository.get_subrace(character.race_id, data.subrace_id) is None:
                    raise SubraceNotFoundException(race_id=character.race_id, subrace_id=data.subrace_id)

            character.subrace_id = data.subrace_id
            await sync_progression_features(self.db, character)
            await self._finish(character)

    async def set_background(self, character_id: int, data: BackgroundChange, current_user: UserResponse) -> None:
        """
        Set a character's background — only while it has none. In one
        transaction it grants the background's features
        (``sync_progression_features``), its skills as BACKGROUND-sourced
        proficiency rows, and its starting equipment (merged into stacks). A
        background whose equipment is built on "pick N of M" choice groups is
        rejected up front (no late-choice surface). Re-choosing is only
        possible through :meth:`rebuild_character`.
        """

        character = await self.get_character_for_user(character_id, current_user)

        async with self._unit_of_work():
            await self._lock_character(character)

            if character.background_id is not None:
                raise BackgroundAlreadySetException(character_id=character.id, background_id=character.background_id)

            background = await self.background_repository.get_by_id(data.background_id)
            if background is None:
                raise BackgroundNotFoundException(background_id=data.background_id)

            await self.background_grants.ensure_no_item_choices(background.id)

            character.background_id = data.background_id
            await sync_progression_features(self.db, character)
            await self.background_grants.grant_skills(character, [skill.id for skill in background.granted_skills])
            await self.background_grants.grant_equipment(character)
            await self._finish(character)

    async def rebuild_character(
        self, character_id: int, data: CharacterRebuildRequest, current_user: UserResponse
    ) -> None:
        """
        Point-rebuild: replace the character's class/subclass/race/subrace/
        background and base ability scores, re-validate and re-apply the
        class skill choices and every reached ASI level, then recompute
        everything that derives from them in one transaction — see
        :class:`~app.features.characters.progression.rebuild.CharacterRebuilder`
        for the exact rules. ``level``, notes, personality, backstory,
        inventory, GM adjustments and GM-granted feats are left untouched.
        """

        character = await self.get_character_for_user(character_id, current_user)
        plan = await self.rebuilder.prepare(data)

        async with self._unit_of_work():
            await self._lock_character(character)
            check_rebuild_asi_levels(character.level, data.asi_choices)

            totals = await self.rebuilder.apply(character, data, plan)
            await self._finish(character, totals)

    async def level_up(self, character_id: int, data: LevelUpRequest, current_user: UserResponse) -> None:
        """
        Advance a character exactly one level, only while below the GM-set
        maximum (``character_max_levels``). At an ASI level (4/8/12/16/19) a
        ``choice`` is required, at any other level it is rejected; a chosen
        feat must be takeable at the new level (``min_level``) and neither
        ASI nor feat pick may push a score above 20. HP defaults to the
        class's standard average (half hit die + 1 + CON) unless
        ``hit_points_gained`` is given (bounded by the hit die + CON), using
        the CON the character has once everything this level grants is
        applied. Features unlocked by the new level are granted; a chosen
        feat's own choice groups (beyond its ASI pick) count too. Any of
        them still left with an unanswered "pick N of M" group after
        applying ``data.feature_choices`` aborts the whole level-up
        (``GrantChoiceRequiredException``). Spell slots are re-applied.
        Leveling up fully heals: ``current_hp`` is set to the new
        ``max_hp`` and ``temp_hp`` clears.
        """

        character = await self.get_character_for_user(character_id, current_user)

        async with self._unit_of_work():
            await self._lock_character(character)

            max_level = await self._allowed_max_level(character)
            if character.level >= max_level:
                raise CharacterAlreadyAtMaxLevelException(character.id, max_level)

            new_level = character.level + 1
            check_level_up_choice(new_level, data.choice is not None)
            character.level = new_level

            feat_grant = None
            if data.choice is not None:
                totals = await self.stats_service.compute(character)
                if data.choice.type == ASILevelChoice.ASI:
                    await self.asi.apply_asi(character, data.choice.increases, new_level, totals)
                else:
                    feat_grant = await self.asi.apply_feat(character, data.choice, new_level, totals)

            new_grants = await sync_progression_features(self.db, character)
            if feat_grant is not None:
                new_grants.append(feat_grant)
            await self.grant_service.resolve_grants_choices(new_grants, self._answers_by_feature(data.feature_choices))

            totals = await self.stats_service.compute(character)
            hp_gain = resolve_hp_gain(
                data.hit_points_gained, await self._hit_die_sides(character.class_id), constitution_modifier(totals)
            )
            character.max_hp += hp_gain
            character.current_hp = character.max_hp
            character.temp_hp = 0

            await self.character_service.reapply_spell_slot_progression(character, commit=False)
            await self._finish(character, totals)

    async def get_asi_choices(self, character_id: int, current_user: UserResponse) -> list[CharacterASIChoiceResponse]:
        """Return the character's resolved ASI-level choices, for audit."""

        await self.get_character_for_user(character_id, current_user)
        choices = await self.asi.asi_repository.get_character_choices(character_id)

        return [CharacterASIChoiceResponse.model_validate(choice) for choice in choices]

    async def can_level_up(self, character_id: int, current_user: UserResponse) -> CanLevelUpResponse:
        """
        Report whether the character may take another level-up: it is
        possible while the character's level is below the GM-set maximum
        (``character_max_levels``).
        """

        character = await self.get_character_for_user(character_id, current_user)
        max_level = await self._allowed_max_level(character)

        return CanLevelUpResponse(
            can_level_up=character.level < max_level,
            current_level=character.level,
            max_level=max_level,
        )

    async def _lock_character(self, character: Character) -> None:
        """
        ``SELECT ... FOR UPDATE`` the character row, refreshing the instance
        from it, so two concurrent writes (a double click) serialize and the
        second validates against the first one's result.
        """

        await self.repository.get_for_update(character.id)

    async def _finish(self, character: Character, totals: dict[str, int] | None = None) -> None:
        """
        Store the ability-score cache (from ``totals`` already computed by the
        use case, else computed now) in the transaction and schedule the
        character's Redis purge for after the commit.
        """

        if totals is None:
            totals = await self.stats_service.compute(character)
        await self.stats_service.store(character, totals, commit=False)
        await self._invalidate_character(character.id)

    async def _allowed_max_level(self, character: Character) -> int:
        """
        The maximum level the character may reach, from its
        ``character_max_levels`` row. A missing row is treated defensively as
        capped at the character's current level — characters always get a
        row at creation and via the migration backfill.
        """

        row = await self.max_level_repository.get_by_character_id(character.id)
        return row.max_level if row is not None else default_max_level(character.level)

    async def _hit_die_sides(self, class_id: int) -> int:
        """Hit die sides of a class (a single-column read, not the whole class tree)."""

        hit_dice = (await self.db.execute(select(Class.hit_dice).where(Class.id == class_id))).scalar_one_or_none()
        if hit_dice is None:
            raise ClassNotFoundException(class_id=class_id)

        return hit_die_sides(hit_dice)

    @staticmethod
    def _answers_by_feature(answers: list[LevelUpFeatureChoiceAnswer]) -> dict[int, list[ChoiceAnswerItem]]:
        """Group the level-up's feature-choice answers by the feature they belong to."""

        grouped: dict[int, list[ChoiceAnswerItem]] = {}
        for answer in answers:
            grouped.setdefault(answer.feature_id, []).append(
                ChoiceAnswerItem(choice_group_id=answer.choice_group_id, choice_option_id=answer.choice_option_id)
            )
        return grouped
