# Shared Tag dictionary. Must come before any catalog's *_tags link table (FK target).
from app.models.articles.article_association_models import article_tags  # noqa: F401

# Article and its associations (incl. article_tags, self-referential parent/children).
from app.models.articles.article_image_model import ArticleImage  # noqa: F401
from app.models.articles.article_model import Article  # noqa: F401
from app.models.articles.article_relation_model import ArticleRelation  # noqa: F401
from app.models.articles.article_subtype_model import ArticleSubtype  # noqa: F401
from app.models.backgrounds.background_association_models import background_skills, background_tags  # noqa: F401

# Background and its associations.
from app.models.backgrounds.background_model import Background  # noqa: F401
from app.models.backgrounds.background_suggestion_model import BackgroundSuggestion  # noqa: F401
from app.models.character.character_ability_score_model import CharacterAbilityScore  # noqa: F401
from app.models.character.character_asi_choice_model import CharacterASIChoice, CharacterASIChoiceIncrease  # noqa: F401
from app.models.character.character_attack_model import Attack  # noqa: F401

# CharacterBackstory: FK/relationship targets are string-based, so no import
# ordering constraint — grouped here with the other character association models.
from app.models.character.character_backstory_model import CharacterBackstory  # noqa: F401
from app.models.character.character_condition_model import CharacterCondition  # noqa: F401
from app.models.character.character_feature_choice_model import CharacterFeatureChoice  # noqa: F401
from app.models.character.character_feature_model import CharacterFeature  # noqa: F401
from app.models.character.character_item_model import CharacterItem  # noqa: F401

# Character and everything that depends on it.
from app.models.character.character_max_level_model import CharacterMaxLevel  # noqa: F401
from app.models.character.character_model import Character  # noqa: F401
from app.models.character.character_proficiency_model import CharacterProficiency  # noqa: F401
from app.models.character.character_spell_model import (  # noqa: F401
    CharacterGrantedSpell,
    CharacterSpell,
    CharacterSpellSlot,
)
from app.models.classes.class_association_models import (  # noqa: F401
    ClassArmorProficiency,
    ClassSavingThrow,
    ClassWeaponProficiency,
    class_available_skills,
)

# Class, subclasses and their associations.
from app.models.classes.class_model import Class  # noqa: F401
from app.models.classes.class_spell_slot_progression_model import ClassSpellSlotProgression  # noqa: F401

# Subclass must be imported after Class (FK dependency) and before Feature (FK target).
from app.models.classes.subclass_model import Subclass  # noqa: F401

# Feature engine (Phase 1): reference-side choice groups/options + effect tables.
# Must come after Feature (FK target) and after Skill/Item/Spell (FK targets);
# those are imported below — mapper configuration tolerates the ordering.
from app.models.features.feature_engine_models import (  # noqa: F401
    FeatureAbilityScoreEffect,
    FeatureArmorProficiencyEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSavingThrowEffect,
    FeatureSkillProficiencyEffect,
    FeatureSpellGrantEffect,
    FeatureWeaponProficiencyEffect,
)

# Feature (class/subclass/race/subrace/background features and feats).
# Must come after Subclass/Subrace so the subclass_id/subrace_id FKs resolve correctly.
from app.models.features.feature_model import Feature  # noqa: F401

# Item and character inventory.
from app.models.items.item_model import Item  # noqa: F401

# Source-owned starting equipment (classes/backgrounds).
from app.models.items.item_source_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption  # noqa: F401
from app.models.items.item_source_model import SourceItem  # noqa: F401
from app.models.races.race_association_models import RaceAbilityBonus, race_skills, race_tags  # noqa: F401

# Race and its associations.
from app.models.races.race_model import Race  # noqa: F401

# Subrace and its associations (incl. subrace_tags).
# Must come after Class/Race (FK targets) and before Feature (FK target).
from app.models.races.subrace_association_models import SubraceAbilityBonus, subrace_tags  # noqa: F401
from app.models.races.subrace_model import Subrace  # noqa: F401
from app.models.skill_model import Skill  # noqa: F401

# Spell.
from app.models.spells.spell_model import Spell  # noqa: F401
from app.models.tag_model import Tag  # noqa: F401
from app.models.user_model import User  # noqa: F401
from app.settings import settings  # noqa: F401
