"""Service for character progression: race/class change and leveling up."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.constants import ABILITY_SCORE_CAP, ASI_LEVELS, ASILevelChoice, CharacterFeatSource
from app.features.characters.ability_score.calculator import BASE_FIELD_BY_ABILITY, TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.core.service import CharacterService
from app.features.characters.feats.exceptions import CharacterFeatAlreadyKnownException
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.validation import check_feat_prerequisite, validate_ability_score_increase
from app.features.characters.progression.exceptions import (
    AbilityScoreCapExceededException,
    CharacterAlreadyAtMaxLevelException,
    InvalidHitPointGainException,
    LevelUpChoiceNotAllowedException,
    LevelUpChoiceRequiredException,
)
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.characters.progression.schemas import (
    CharacterASIChoiceResponse,
    ClassChange,
    LevelUpRequest,
    RaceChange,
    SubclassChange,
)
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.classes.repository import ClassRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.features.feats.repository import FeatRepository
from app.features.races.exceptions import RaceNotFoundException
from app.features.races.repository import RaceRepository
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


class CharacterProgressionService(CharacterSubDomainService):
    """
    Character progression: race change, class change, subclass change,
    and leveling up.

    Leveling up is the entry point for ability score improvements: an
    ASI level (see ``ASI_LEVELS``) *requires* a ``choice`` in the
    request, and the resolved ASI-or-feat is recorded in
    ``character_asi_choices`` for audit and future level-down support.

    Source-owned feature grants are kept in sync automatically: every
    level-up, race change, class change, and subclass change reconciles
    ``character_features`` against the CLASS features of the character's
    class plus the SUBCLASS features of its subclass, its RACE and
    BACKGROUND features, and the FEAT features of every granted feat (see
    ``sync_progression_features``).

    Writes are transactional: the level bump, HP gain, ASI/feat grant,
    audit row, feature grants, and spell-slot re-application all happen
    in one commit (via :meth:`_atomic`); any validation failure rolls the
    whole thing back.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.character_service = CharacterService(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.feat_repository = FeatRepository(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.asi_repository = CharacterASIChoiceRepository(db)
        self.stats_service = CharacterStatsService(db)

    @contextmanager
    def _atomic(self) -> Iterator[None]:
        """
        Wrap a set of writes in one transaction: run everything inside a
        savepoint, then commit on success or roll back (discarding the
        savepoint) on any exception.
        """
        db = self.repository.db
        try:
            with db.begin_nested():
                yield
            db.commit()
        except Exception:
            db.rollback()
            raise

    def change_race(self, character_id: int, data: RaceChange, current_user: UserResponse) -> None:
        """
        Update a character's ``race_id`` (``None`` clears it).

        The new race's features are granted (the old race's auto-granted
        features revoked) in the same transaction, then the ability score
        cache is refreshed to re-derive race bonuses.
        """
        character = self.get_character_for_user(character_id, current_user)
        if data.race_id is not None and not self.race_repository.exists_by_id(data.race_id):
            raise RaceNotFoundException(race_id=data.race_id)

        with self._atomic():
            character.race_id = data.race_id
            sync_progression_features(self.repository.db, character)

        self.stats_service.refresh(character)

    def change_class(self, character_id: int, data: ClassChange, current_user: UserResponse) -> None:
        """
        Replace a character's class (no multiclassing).

        The current subclass is kept only if it belongs to the new class
        (otherwise cleared), granted class/subclass features are
        reconciled to the new class at the current level, and the new
        class's spell slot progression is re-applied. All of it commits
        in one transaction.
        """
        character = self.get_character_for_user(character_id, current_user)
        if not self.class_repository.exists_by_id(data.class_id):
            raise ClassNotFoundException(class_id=data.class_id)

        with self._atomic():
            character.class_id = data.class_id

            if character.subclass_id is not None:
                if self.class_repository.get_subclass(data.class_id, character.subclass_id) is None:
                    character.subclass_id = None

            sync_progression_features(self.repository.db, character)
            self.character_service.reapply_spell_slot_progression(character, commit=False)

    def set_subclass(self, character_id: int, data: SubclassChange, current_user: UserResponse) -> None:
        """
        Set or clear a character's subclass.

        ``subclass_id`` must reference a subclass of the character's
        current class — otherwise ``SubclassNotFoundException``.
        Setting a subclass grants its features at or below the current
        level; clearing it revokes that subclass's auto-granted features.
        """
        character = self.get_character_for_user(character_id, current_user)

        if (
            data.subclass_id is not None
            and self.class_repository.get_subclass(character.class_id, data.subclass_id) is None
        ):
            raise SubclassNotFoundException(class_id=character.class_id, subclass_id=data.subclass_id)

        with self._atomic():
            character.subclass_id = data.subclass_id
            sync_progression_features(self.repository.db, character)

    def level_up(self, character_id: int, data: LevelUpRequest, current_user: UserResponse) -> None:
        """
        Advance a character exactly one level.

        At an ASI level (4/8/12/16/19) a ``choice`` is required and at
        any other level it is rejected. HP defaults to the class's
        standard average (half hit die + 1 + CON modifier) unless
        ``hit_points_gained`` is given (bounded by the hit die + CON).
        Class/subclass features unlocked by the new level are granted,
        and spell slots are re-applied.
        """
        character = self.get_character_for_user(character_id, current_user)
        if character.level >= ABILITY_SCORE_CAP:
            raise CharacterAlreadyAtMaxLevelException(character_id)

        new_level = character.level + 1
        is_asi_level = new_level in ASI_LEVELS

        if is_asi_level and data.choice is None:
            raise LevelUpChoiceRequiredException(class_level=new_level)
        if not is_asi_level and data.choice is not None:
            raise LevelUpChoiceNotAllowedException(class_level=new_level)

        with self._atomic():
            character.level = new_level

            if data.choice is not None:
                if data.choice.type == ASILevelChoice.ASI:
                    self._apply_asi(character, data.choice.increases, new_level)
                else:
                    self._apply_feat(character, data.choice, new_level)

            hp_gain = self._resolve_hp_gain(character, data.hit_points_gained)
            character.max_hp += hp_gain

            # Grant any class/subclass features unlocked by the new level.
            sync_progression_features(self.repository.db, character)
            self.character_service.reapply_spell_slot_progression(character, commit=False)

        self.stats_service.refresh(character)

    def get_asi_choices(self, character_id: int, current_user: UserResponse) -> list[CharacterASIChoiceResponse]:
        """Return the character's resolved ASI-level choices, for audit."""
        self.get_character_for_user(character_id, current_user)
        choices = self.asi_repository.get_character_choices(character_id)
        return [CharacterASIChoiceResponse.model_validate(choice) for choice in choices]

    def _apply_asi(self, character: Character, increases, class_level: int) -> None:
        """
        Apply an Ability Score Improvement: validate against the 20 cap
        using the character's *effective* scores, then bump the base
        columns and record the choice.
        """
        totals = self.stats_service.compute(character)
        for item in increases:
            total_field = TOTAL_FIELD_BY_ABILITY[item.ability]
            current_total = totals[total_field]
            if current_total + item.amount > ABILITY_SCORE_CAP:
                raise AbilityScoreCapExceededException(
                    ability=item.ability.value,
                    current_total=current_total,
                    requested=current_total + item.amount,
                )

        for item in increases:
            base_field = BASE_FIELD_BY_ABILITY[item.ability]
            setattr(character, base_field, getattr(character, base_field) + item.amount)

        self.asi_repository.add(
            character.id,
            class_level,
            ASILevelChoice.ASI,
            increases=[{"ability": item.ability.value, "amount": item.amount} for item in increases],
            commit=False,
        )

    def _apply_feat(self, character: Character, choice, class_level: int) -> None:
        """
        Apply a feat-as-ASI: validate the feat exists, isn't already
        known, has a valid ASI pick (if any) and the prerequisite is met,
        then grant it (source ``ASI``) and record the choice.
        """
        feat = self.feat_repository.get_by_id(choice.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=choice.feat_id)

        existing = self.feat_grant_repository.get_character_feat_by_feat_id(character.id, choice.feat_id)
        if existing:
            raise CharacterFeatAlreadyKnownException(character_id=character.id, feat_id=choice.feat_id)

        if choice.ability_score_increase_id is not None:
            validate_ability_score_increase(feat, choice.ability_score_increase_id)
        check_feat_prerequisite(character, feat, self.stats_service)

        self.feat_grant_repository.add_character_feat(
            character.id,
            choice.feat_id,
            choice.ability_score_increase_id,
            source_type=CharacterFeatSource.ASI,
            commit=False,
        )
        self.asi_repository.add(
            character.id,
            class_level,
            ASILevelChoice.FEAT,
            feat_id=choice.feat_id,
            ability_score_increase_id=choice.ability_score_increase_id,
            commit=False,
        )

    def _resolve_hp_gain(self, character: Character, requested: int | None) -> int:
        """Default HP gain is half hit die + 1 + CON modifier; a provided value must fit the die + CON bounds."""
        die_sides = self._class_die_sides(character)
        con_mod = self._constitution_modifier(character)
        if requested is None:
            return die_sides // 2 + 1 + con_mod
        max_gain = die_sides + con_mod
        if requested < 1 or requested > max_gain:
            raise InvalidHitPointGainException(minimum=1, maximum=max_gain)
        return requested

    def _class_die_sides(self, character: Character) -> int:
        """Hit die sides of the character's class (e.g. ``"D8"`` -> 8)."""
        character_class = self.class_repository.get_by_id(character.class_id)
        if character_class is None:
            return 0
        return int(character_class.hit_dice.value[1:])

    def _constitution_modifier(self, character: Character) -> int:
        """CON modifier from the character's current *effective* CON total."""
        totals = self.stats_service.compute(character)
        return (totals["constitution_total"] - 10) // 2
