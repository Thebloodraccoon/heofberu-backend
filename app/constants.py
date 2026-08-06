"""
Shared enums and helper constants used across the application.

Contains the canonical domain enumerations (roles, dice, spell and item
metadata, conditions, ...) together with backward-compatible string lists
and helpers that build raw SQL check constraints.
"""

from enum import Enum


class UserRole(str, Enum):
    """Role of a registered user: GM or player."""

    GM = "gm"
    PLAYER = "player"


class RaceSize(str, Enum):
    """Creature size category of a race, from Tiny to Gargantuan."""

    TINY = "TINY"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    HUGE = "HUGE"
    GARGANTUAN = "GARGANTUAN"


class AbilityScore(str, Enum):
    """The six D&D ability scores (Strength through Charisma)."""

    STR = "STR"
    DEX = "DEX"
    CON = "CON"
    INT = "INT"
    WIS = "WIS"
    CHA = "CHA"


class DiceType(str, Enum):
    """Standard polyhedral die types used for damage and ability rolls."""

    D4 = "D4"
    D6 = "D6"
    D8 = "D8"
    D10 = "D10"
    D12 = "D12"
    D20 = "D20"
    D100 = "D100"


class AttackType(str, Enum):
    """Category of an attack: melee or ranged."""

    MELEE_ATTACK = "MELEE_ATTACK"
    RANGED_ATTACK = "RANGED_ATTACK"


class SpellLevel(str, Enum):
    """Spell level, including cantrips (level 0)."""

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
    """The eight schools of magic."""

    ABJURATION = "ABJURATION"
    CONJURATION = "CONJURATION"
    DIVINATION = "DIVINATION"
    ENCHANTMENT = "ENCHANTMENT"
    EVOCATION = "EVOCATION"
    ILLUSION = "ILLUSION"
    NECROMANCY = "NECROMANCY"
    TRANSMUTATION = "TRANSMUTATION"


class SpellCastTime(str, Enum):
    """Time required to cast a spell (action, bonus action, reaction, special)."""

    ACTION = "ACTION"
    BONUS_ACTION = "BONUS_ACTION"
    REACTION = "REACTION"
    SPECIAL = "SPECIAL"


class SpellDuration(str, Enum):
    """Duration of a spell's effect (instantaneous to until dispelled)."""

    INSTANTANEOUS = "INSTANTANEOUS"
    ONE_ROUND = "ONE_ROUND"
    ONE_MINUTE = "ONE_MINUTE"
    TEN_MINUTES = "TEN_MINUTES"
    ONE_HOUR = "ONE_HOUR"
    EIGHT_HOURS = "EIGHT_HOURS"
    TWENTY_FOUR_HOURS = "TWENTY_FOUR_HOURS"
    SEVEN_DAYS = "SEVEN_DAYS"
    THIRTY_DAYS = "THIRTY_DAYS"
    UNTIL_DISPELLED = "UNTIL_DISPELLED"
    SPECIAL = "SPECIAL"


class Component(str, Enum):
    """Spell components: verbal, somatic, material."""

    VERBAL = "VERBAL"
    SOMATIC = "SOMATIC"
    MATERIAL = "MATERIAL"


class SpellRangeType(str, Enum):
    """Spell range category: self, touch, ranged, sight, unlimited."""

    SELF = "SELF"
    TOUCH = "TOUCH"
    RANGED = "RANGED"
    SIGHT = "SIGHT"
    UNLIMITED = "UNLIMITED"


class DamageType(str, Enum):
    """Damage types: physical (slashing, piercing, bludgeoning) and elemental."""

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


class HealingTarget(str, Enum):
    """What a healing effect restores: HP or temporary HP."""

    HP = "HP"
    TEMP_HP = "TEMP_HP"


class ItemType(str, Enum):
    """Categories of items: weapons, armor, consumables, magic items, etc."""

    WEAPON = "WEAPON"
    ARMOR = "ARMOR"
    SHIELD = "SHIELD"
    POTION = "POTION"
    SCROLL = "SCROLL"
    WONDROUS_ITEM = "WONDROUS_ITEM"
    RING = "RING"
    ROD = "ROD"
    STAFF = "STAFF"
    WAND = "WAND"
    ADVENTURING_GEAR = "ADVENTURING_GEAR"
    TOOL = "TOOL"
    AMMUNITION = "AMMUNITION"
    TREASURE = "TREASURE"
    OTHER = "OTHER"


class ItemRarity(str, Enum):
    """Rarity of a magic item; NONE marks non-magical mundane items."""

    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    VERY_RARE = "VERY_RARE"
    LEGENDARY = "LEGENDARY"
    ARTIFACT = "ARTIFACT"
    NONE = "NONE"  # non-magical mundane items


class FeatureSourceType(str, Enum):
    """Origin of a feature: class, subclass, race, background, feat, other."""

    CLASS = "CLASS"
    SUBCLASS = "SUBCLASS"
    RACE = "RACE"
    BACKGROUND = "BACKGROUND"
    FEAT = "FEAT"
    OTHER = "OTHER"


class ASILevelChoice(str, Enum):
    """What a character chose at a class level that grants an Ability Score Improvement."""

    ASI = "ASI"
    FEAT = "FEAT"


class CharacterFeatSource(str, Enum):
    """Where a character's feat grant came from: GM grant, level-1 origin feat, or an ASI-level choice."""

    GM = "GM"
    ORIGIN = "ORIGIN"
    ASI = "ASI"


class ConditionType(str, Enum):
    """The standard D&D conditions a creature can be under."""

    BLINDED = "BLINDED"
    CHARMED = "CHARMED"
    DEAFENED = "DEAFENED"
    FRIGHTENED = "FRIGHTENED"
    GRAPPLED = "GRAPPLED"
    INCAPACITATED = "INCAPACITATED"
    INVISIBLE = "INVISIBLE"
    PARALYZED = "PARALYZED"
    PETRIFIED = "PETRIFIED"
    POISONED = "POISONED"
    PRONE = "PRONE"
    RESTRAINED = "RESTRAINED"
    STUNNED = "STUNNED"
    UNCONSCIOUS = "UNCONSCIOUS"
    EXHAUSTION = "EXHAUSTION"


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
HEALING_TARGETS = [target.value for target in HealingTarget]
ITEM_TYPES = [item_type.value for item_type in ItemType]
ITEM_RARITIES = [rarity.value for rarity in ItemRarity]
FEATURE_SOURCE_TYPES = [source_type.value for source_type in FeatureSourceType]
ASI_LEVEL_CHOICES = [choice.value for choice in ASILevelChoice]
CHARACTER_FEAT_SOURCES = [source.value for source in CharacterFeatSource]
CONDITION_TYPES = [condition_type.value for condition_type in ConditionType]

# Class levels (5e standard) at which a character gains an Ability Score
# Improvement and may instead choose a feat. Same for every class; keep as a
# single constant so a future per-class table can swap in without touching
# the progression service.
ASI_LEVELS = frozenset({4, 8, 12, 16, 19})

# Maximum effective (post-bonus) ability score, per the 5e rule.
ABILITY_SCORE_CAP = 20

ON_DELETE_SET_NULL = "SET NULL"
ON_DELETE_CASCADE = "CASCADE"
ON_DELETE_RESTRICT = "RESTRICT"


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
