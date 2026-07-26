from enum import Enum


class UserRole(str, Enum):
    GM = "gm"
    PLAYER = "player"


class RaceSize(str, Enum):
    TINY = "Крошечный"
    SMALL = "Маленький"
    MEDIUM = "Средний"
    LARGE = "Большой"
    HUGE = "Огромный"
    GARGANTUAN = "Гигантский"


class AbilityScore(str, Enum):
    STR = "STR"
    DEX = "DEX"
    CON = "CON"
    INT = "INT"
    WIS = "WIS"
    CHA = "CHA"


class AttackType(str, Enum):
    MELEE_ATTACK = "MELEE_ATTACK"
    RANGED_ATTACK = "RANGED_ATTACK"


class SpellLevel(str, Enum):
    CANTRIP = "CANTRIP"
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    LEVEL_4 = "LEVEL_4"
    LEVEL_5 = "LEVEL_5"
    LEVEL_6 = "LEVEL_6"
    LEVEL_7 = "LEVEL_7"
    LEVEL_8 = "LEVEL_8"
    LEVEL_9 = "LEVEL_9"


class SpellSchool(str, Enum):
    ABJURATION = "ABJURATION"
    CONJURATION = "CONJURATION"
    DIVINATION = "DIVINATION"
    ENCHANTMENT = "ENCHANTMENT"
    EVOCATION = "EVOCATION"
    ILLUSION = "ILLUSION"
    NECROMANCY = "NECROMANCY"
    TRANSMUTATION = "TRANSMUTATION"


class SpellRangeType(str, Enum):
    SELF = "SELF"
    TOUCH = "TOUCH"
    RANGED = "RANGED"
    SIGHT = "SIGHT"
    UNLIMITED = "UNLIMITED"


class DamageType(str, Enum):
    SLASHING = "SLASHING"
    PIERCING = "PIERCING"
    BLUDGEONING = "BLUDGEONING"
    ACID = "ACID"
    COLD = "COLD"
    FIRE = "FIRE"
    FORCE = "FORCE"
    LIGHTNING = "LIGHTNING"
    NECROTIC = "NECROTIC"
    POISON = "POISON"
    PSYCHIC = "PSYCHIC"
    RADIANT = "RADIANT"
    THUNDER = "THUNDER"


# Kept as plain lists for backward compatibility with existing CheckConstraints
# and any code still importing the raw string lists.
USER_ROLES = [role.value for role in UserRole]
RACE_SIZES = [size.value for size in RaceSize]
ABILITY_SCORES = [score.value for score in AbilityScore]
ATTACK_TYPES = [attack_type.value for attack_type in AttackType]
SPELL_LEVELS = [level.value for level in SpellLevel]
SPELL_SCHOOLS = [school.value for school in SpellSchool]
SPELL_RANGE_TYPES = [range_type.value for range_type in SpellRangeType]
DAMAGE_TYPES = [damage_type.value for damage_type in DamageType]

ON_DELETE_SET_NULL = "SET NULL"
ON_DELETE_CASCADE = "CASCADE"


def create_enum_constraint(field_name: str, values: list, nullable: bool = True) -> str:
    """Creates a line for CheckContraint with ENUM values."""
    values_str = ", ".join(repr(v) for v in values)

    if nullable:
        return f"{field_name} IS NULL OR {field_name} IN ({values_str})"
    else:
        return f"{field_name} IN ({values_str})"


def create_range_constraint(field_name: str, min_val: int, max_val: int, nullable: bool = True) -> str:
    """Creates a line for CheckContraint with a numerical range."""
    constraint = f"({field_name} >= {min_val} AND {field_name} <= {max_val})"

    if nullable:
        return f"{field_name} IS NULL OR {constraint}"
    else:
        return constraint
