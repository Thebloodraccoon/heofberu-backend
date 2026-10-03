"""
Shared enums and helper constants used across the application.

Contains the canonical domain enumerations (roles, dice, spell and item
metadata, conditions, ...) together with shared string lists and numeric limits.
"""

from enum import Enum


class UserRole(str, Enum):
    """Role of a registered user: found father (founder), GM, or player."""

    FOUND_FATHER = "found_father"
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
    """Time required to cast a spell (action, bonus action, reaction, rituals-length casts, special)."""

    ACTION = "ACTION"
    BONUS_ACTION = "BONUS_ACTION"
    REACTION = "REACTION"
    ONE_MINUTE = "ONE_MINUTE"
    TEN_MINUTES = "TEN_MINUTES"
    ONE_HOUR = "ONE_HOUR"
    EIGHT_HOURS = "EIGHT_HOURS"
    TWELVE_HOURS = "TWELVE_HOURS"
    TWENTY_FOUR_HOURS = "TWENTY_FOUR_HOURS"
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
    """
    Origin of a feature: class, subclass, race, subrace, background, feat, other.

    ``FEAT`` was briefly removed as a feature source (a feat used to be "de
    facto its own feature" living in a parallel ``feats`` table). Under the
    unified Feature/Feat engine it is a real source again: a row with
    ``source_type=FEAT`` carries no source FK, instead holding the
    feat-specific ``min_level`` / ``prerequisite_*`` columns. The value has
    always remained in the Postgres ENUM type (Postgres cannot drop enum
    values), so no DB enum surgery is needed.
    """

    CLASS = "CLASS"
    SUBCLASS = "SUBCLASS"
    RACE = "RACE"
    SUBRACE = "SUBRACE"
    BACKGROUND = "BACKGROUND"
    FEAT = "FEAT"
    OTHER = "OTHER"


class GrantSource(str, Enum):
    """
    Where a character's feature grant came from.

    Replaces ``CharacterFeatSource`` and the old implicit
    "``source_type`` in ``_AUTO_SOURCE_TYPES``" derivation with one explicit
    axis on ``character_features``:

    - ``AUTO`` — synchronized automatically from ownership of a
      class/subclass/race/subrace/background (progression sync).
    - ``GM`` — manual grant from the GM panel.
    - ``ASI`` — taken instead of an Ability Score Improvement at level-up.
    """

    AUTO = "AUTO"
    GM = "GM"
    ASI = "ASI"


class ArmorProficiency(str, Enum):
    """Armor categories a class grants proficiency in (5e-style)."""

    LIGHT = "LIGHT"
    MEDIUM = "MEDIUM"
    HEAVY = "HEAVY"
    SHIELD = "SHIELD"


class WeaponProficiency(str, Enum):
    """Weapon categories a class grants proficiency in (5e-style)."""

    SIMPLE = "SIMPLE"
    MARTIAL = "MARTIAL"


class ProficiencyType(str, Enum):
    """Which of a character's four proficiency kinds a row concerns — the discriminator on ``character_proficiencies``."""

    SKILL = "SKILL"
    SAVING_THROW = "SAVING_THROW"
    ARMOR = "ARMOR"
    WEAPON = "WEAPON"


class ChoiceType(str, Enum):
    """
    What kind of effect a ``FeatureChoiceGroup``'s options carry — fixed at
    the group, and enforced on every option in it: an option in a ``SKILL``
    group may only populate ``skill_effects``, an ``ABILITY_SCORE`` group
    only ``ability_effects``, and so on. One effect type per group, no mixed
    bundles.
    """

    SKILL = "SKILL"
    SPELL = "SPELL"
    ABILITY_SCORE = "ABILITY_SCORE"
    SAVING_THROW = "SAVING_THROW"
    ARMOR = "ARMOR"
    WEAPON = "WEAPON"


class ProficiencySourceType(str, Enum):
    """
    How a ``character_proficiencies`` row came to exist — a second axis
    alongside ``proficiency_type``.

    - ``CLASS`` — auto-granted by the class (e.g. its fixed saving throws),
      no choice involved. Distinct from ``CLASS_CHOICE``: this is for the
      class's own non-choice grants, not yet routed through the feature
      engine (``class_saving_throws`` isn't itself a Feature source).
    - ``CLASS_CHOICE`` — the player's skill pick at character creation from
      the class's ``available_skills``.
    - ``RACE`` — auto-granted by the race's ``granted_skills`` (no choice).
    - ``BACKGROUND`` — auto-granted by the background's granted skills.
    - ``FEATURE`` — a fixed (non-choice) effect of a granted feature/feat.
    - ``FEATURE_CHOICE`` — the player resolved a choice group inside a
      granted feature/feat.
    - ``GM`` — a manual GM-panel add/remove/expertise edit. At most one
      ``GM`` row exists per (character, proficiency) — see
      :class:`ProficiencyAction`.
    """

    CLASS = "CLASS"
    CLASS_CHOICE = "CLASS_CHOICE"
    RACE = "RACE"
    BACKGROUND = "BACKGROUND"
    FEATURE = "FEATURE"
    FEATURE_CHOICE = "FEATURE_CHOICE"
    GM = "GM"


class ProficiencyAction(str, Enum):
    """
    What a ``character_proficiencies`` row does — only meaningful for
    ``source_type=GM`` rows (every other source only ever grants). A GM row
    is upserted in place, never appended, so exactly one reflects the GM's
    latest decision for a given (character, proficiency).

    - ``GRANT`` — the GM hands the character this proficiency outright,
      independent of any other source.
    - ``REVOKE`` — the GM vetoes this proficiency even though another
      source (class/race/background/feature) would otherwise grant it;
      wins over every other source when resolving current state.
    """

    GRANT = "GRANT"
    REVOKE = "REVOKE"


class ASILevelChoice(str, Enum):
    """What a character chose at a class level that grants an Ability Score Improvement."""

    ASI = "ASI"
    FEAT = "FEAT"


class CharacterFeatSource(str, Enum):
    """
    Where a character's feat grant came from: a GM panel grant or an ASI-level choice.

    Retained for the response shape (``CharacterFeatResponse.source_type``);
    new code uses :class:`GrantSource`.
    """

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


class BackgroundSuggestionType(str, Enum):
    """Which personality-card field a ``background_suggestions`` row is a suggested entry for."""

    PERSONALITY_TRAIT = "PERSONALITY_TRAIT"
    IDEAL = "IDEAL"
    BOND = "BOND"
    FLAW = "FLAW"


class ArticleStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ArticleVisibility(str, Enum):
    """Who may read an article: everyone (once published) or only GMs (spoilers, prep notes)."""

    PUBLIC = "public"
    GM_ONLY = "gm_only"


class ArticleProposalStatus(str, Enum):
    """Review state of a proposed change to someone else's article (like a pull request)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


def is_article_publicly_visible(status: "ArticleStatus | str", visibility: "ArticleVisibility | str") -> bool:
    """
    Canonical non-GM visibility predicate, in value form so it applies equally to an
    ORM ``Article``, a cached ``ArticleResponse``, or raw SQL (see
    ``app.features.articles.visibility.visibility_conditions`` for the row-filter equivalent).
    """

    return status == ArticleStatus.PUBLISHED and visibility == ArticleVisibility.PUBLIC


ARTICLE_TYPES = (
    "lore",
    "region",
    "location",
    "faction",
    "npc",
    "event",
    "artifact",
    "deity",
    "religion",
    "creature",
    "culture",
    "language",
    "document",
    "condition",
    "quest",
    "session",
)

#: Postgres ARE for a GM-only block in ``body_markdown``: ``:::gm`` ... ``:::``. An unclosed
#: block hides everything to the end of the text (fail closed). ``(?i)`` = case-insensitive
#: (``:::GM`` too). Flat pattern: nested containers inside ``:::gm`` are rejected on write
#: (``has_nested_gm_container``) and handled in ``app/features/articles/secrets.py``
#: (``strip_gm_blocks``, ``gm_stripped_sql``). Used by generated columns and migrations.
ARTICLE_GM_BLOCK_SQL_PATTERN = "(?i):::gm.*?(:::|$)"
RELATION_TYPES = (
    "LOCATED_IN",
    "MEMBER_OF",
    "RULES",
    "PARENT_FACTION",
    "ALLY_OF",
    "ENEMY_OF",
    "RELATIVE_OF",
    "MENTIONS",
    "SEE_ALSO",
    "PARTICIPATED_IN",
)


# Class levels (5e standard) at which a character gains an Ability Score
# Improvement and may instead choose a feat. Same for every class; keep as a
# single constant so a future per-class table can swap in without touching
# the progression service.
ASI_LEVELS = frozenset({4, 8, 12, 16, 19})

# Standard effective (post-bonus) ability score, per the 5e rule. A feature
# effect may raise a single ability's cap above this (via ``new_cap``) up to
# ``MAX_ABILITY_SCORE_CAP`` — the hard system ceiling (e.g. a GM granting a
# feature that lifts STR to 30).
ABILITY_SCORE_CAP = 20

# Absolute hard ceiling for any single ability score, regardless of how many
# feature effects raise a cap. ``new_cap`` values are clamped to this.
MAX_ABILITY_SCORE_CAP = 30

# Hard ceiling for character levels (also enforced by DB check constraints
# on ``characters.level`` and ``character_max_levels.max_level``).
CHARACTER_MAX_LEVEL = 20

# Max length (characters) of a character's backstory — roughly four pages of
# Word text. Enforced by both the backstory schema (422) and a DB check
# constraint on ``character_backstories.content``.
BACKSTORY_MAX_LENGTH = 12000
