from sqlalchemy import Enum as SAEnum

from app.constants import (
    AbilityScore,
    AttackType,
    DamageType,
    RaceSize,
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
AttackTypeType = SAEnum(AttackType, name="attack_type", create_type=False)
SpellLevelType = SAEnum(SpellLevel, name="spell_level", create_type=False)
SpellSchoolType = SAEnum(SpellSchool, name="spell_school", create_type=False)
SpellRangeTypeType = SAEnum(SpellRangeType, name="spell_range_type", create_type=False)
DamageTypeType = SAEnum(DamageType, name="damage_type", create_type=False)
