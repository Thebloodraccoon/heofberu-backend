from sqlalchemy import Enum as SAEnum

from app.constants import (
    AbilityScore,
    AttackType,
    ConditionType,
    Component,
    DamageType,
    DiceType,
    FeatureSourceType,
    HealingTarget,
    ItemRarity,
    ItemType,
    RaceSize,
    SpellCastTime,
    SpellDuration,
    SpellLevel,
    SpellRangeType,
    SpellSchool,
    UserRole,
)

# Each of these creates/uses a native PostgreSQL ENUM type (via SQLAlchemy's
# Enum construct). `name=` controls the Postgres type name; `create_type=False`
# is used at the model level and the actual `CREATE TYPE` is handled explicitly
# in the Alembic migration so upgrade/downgrade stay in our control.

UserRoleType = SAEnum(UserRole, name="user_role", create_type=False)
RaceSizeType = SAEnum(RaceSize, name="race_size", create_type=False)
AbilityScoreType = SAEnum(AbilityScore, name="ability_score", create_type=False)
DiceTypeColumn = SAEnum(DiceType, name="hit_dice", create_type=False)
AttackTypeType = SAEnum(AttackType, name="attack_type", create_type=False)
SpellLevelType = SAEnum(SpellLevel, name="spell_level", create_type=False)
SpellSchoolType = SAEnum(SpellSchool, name="spell_school", create_type=False)
SpellRangeTypeType = SAEnum(SpellRangeType, name="spell_range_type", create_type=False)
SpellCastTimeType = SAEnum(SpellCastTime, name="spell_cast_time", create_type=False)
SpellDurationType = SAEnum(SpellDuration, name="spell_duration", create_type=False)
DamageTypeType = SAEnum(DamageType, name="damage_type", create_type=False)
HealingTargetType = SAEnum(HealingTarget, name="healing_target", create_type=False)
ItemTypeType = SAEnum(ItemType, name="item_type", create_type=False)
ItemRarityType = SAEnum(ItemRarity, name="item_rarity", create_type=False)
FeatureSourceTypeType = SAEnum(FeatureSourceType, name="feature_source_type", create_type=False)
ConditionTypeType = SAEnum(ConditionType, name="condition_type", create_type=False)
ComponentType = SAEnum(Component, name="spell_component", create_type=False)