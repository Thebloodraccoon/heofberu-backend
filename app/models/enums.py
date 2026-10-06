"""
SQLAlchemy enum column types mapped from the shared domain enums.

Closed sets are native PostgreSQL ENUMs (``create_type=False``, the
``CREATE TYPE`` statements live in the Alembic migrations); sets that grow
with content are stored as ``VARCHAR`` (``native_enum=False``).
"""

from sqlalchemy import Enum as SAEnum

from app.constants import (
    AbilityScore,
    ArmorProficiency,
    ArticleProposalStatus,
    ArticleStatus,
    ArticleVisibility,
    ASILevelChoice,
    AttackType,
    BackgroundSuggestionType,
    ChoiceType,
    Component,
    ConditionType,
    DamageType,
    DiceType,
    FeatureSourceType,
    GrantSource,
    HealingTarget,
    ItemRarity,
    ItemType,
    ProficiencyAction,
    ProficiencySourceType,
    ProficiencyType,
    RaceSize,
    SpellCastTime,
    SpellDuration,
    SpellLevel,
    SpellRangeType,
    SpellSchool,
    UserRole,
    WeaponProficiency,
)

# Each of these creates/uses a native PostgreSQL ENUM type (via SQLAlchemy's
# Enum construct). `name=` controls the Postgres type name; `create_type=False`
# is used at the model level and the actual `CREATE TYPE` is handled explicitly
# in the Alembic migration so upgrade/downgrade stay in our control.
#
# Exception — ``native_enum=False``: plain VARCHAR holding the member NAME, validated in Python only,
# so a new value is a code change with no migration (like ``ARTICLE_TYPES``). Used for sets that grow
# with content or product decisions. ``users.role`` additionally keeps a DB CHECK (``ck_users_role``,
# see ``User``) because it gates permissions.

UserRoleType = SAEnum(UserRole, native_enum=False, create_constraint=False, length=20)
RaceSizeType = SAEnum(RaceSize, name="race_size", create_type=False)
AbilityScoreType = SAEnum(AbilityScore, name="ability_score", create_type=False)
DiceTypeColumn = SAEnum(DiceType, name="hit_dice", create_type=False)
AttackTypeType = SAEnum(AttackType, name="attack_type", create_type=False)
SpellLevelType = SAEnum(SpellLevel, name="spell_level", create_type=False)
SpellSchoolType = SAEnum(SpellSchool, name="spell_school", create_type=False)
SpellRangeTypeType = SAEnum(SpellRangeType, name="spell_range_type", create_type=False)
SpellCastTimeType = SAEnum(SpellCastTime, native_enum=False, create_constraint=False, length=30)
SpellDurationType = SAEnum(SpellDuration, native_enum=False, create_constraint=False, length=30)
DamageTypeType = SAEnum(DamageType, name="damage_type", create_type=False)
HealingTargetType = SAEnum(HealingTarget, name="healing_target", create_type=False)
ItemTypeType = SAEnum(ItemType, native_enum=False, create_constraint=False, length=30)
ItemRarityType = SAEnum(ItemRarity, name="item_rarity", create_type=False)
FeatureSourceTypeType = SAEnum(FeatureSourceType, name="feature_source_type", create_type=False)
ArmorProficiencyType = SAEnum(ArmorProficiency, name="armor_proficiency", create_type=False)
WeaponProficiencyType = SAEnum(WeaponProficiency, name="weapon_proficiency", create_type=False)
ASILevelChoiceType = SAEnum(ASILevelChoice, name="asi_choice", create_type=False)
GrantSourceType = SAEnum(GrantSource, name="feature_grant_source", create_type=False)
ConditionTypeType = SAEnum(ConditionType, name="condition_type", create_type=False)
ComponentType = SAEnum(Component, name="spell_component", create_type=False)
ProficiencyTypeType = SAEnum(ProficiencyType, name="proficiency_type", create_type=False)
ProficiencySourceTypeType = SAEnum(ProficiencySourceType, name="proficiency_source_type", create_type=False)
ProficiencyActionType = SAEnum(ProficiencyAction, name="proficiency_action", create_type=False)
BackgroundSuggestionTypeType = SAEnum(BackgroundSuggestionType, name="background_suggestion_type", create_type=False)
ChoiceTypeType = SAEnum(ChoiceType, name="choice_type", create_type=False)
ArticleStatusType = SAEnum(ArticleStatus, name="article_status", create_type=False)
ArticleVisibilityType = SAEnum(ArticleVisibility, name="article_visibility", create_type=False)
ArticleProposalStatusType = SAEnum(ArticleProposalStatus, name="article_proposal_status", create_type=False)
