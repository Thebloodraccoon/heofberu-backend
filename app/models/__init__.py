from app.models.attack_model import Attack  # noqa: F401
from app.models.background_association_models import background_skills  # noqa: F401

# Background and its associations.
from app.models.background_model import Background  # noqa: F401
from app.models.campaign_character_model import CampaignCharacter  # noqa: F401

# Campaign and its associations.
from app.models.campaign_model import Campaign  # noqa: F401
from app.models.character_ability_score_model import CharacterAbilityScore  # noqa: F401
from app.models.character_asi_choice_model import CharacterASIChoice  # noqa: F401
from app.models.character_association_models import (  # noqa: F401
    CharacterFeat,
    CharacterSkillProficiency,
    CharacterSpellSlot,
)
from app.models.character_condition_model import CharacterCondition  # noqa: F401
from app.models.character_feature_model import CharacterFeature  # noqa: F401
from app.models.character_item_model import CharacterItem  # noqa: F401

# Character and everything that depends on it.
from app.models.character_model import Character  # noqa: F401
from app.models.character_spell_model import CharacterSpell  # noqa: F401
from app.models.class_association_models import (  # noqa: F401
    ClassArmorProficiency,
    ClassPrimaryAbility,
    ClassSavingThrow,
    class_available_skills,
)

# Class, subclasses and their associations.
from app.models.class_model import Class  # noqa: F401
from app.models.class_spell_slot_progression_model import ClassSpellSlotProgression  # noqa: F401

# Feat.
from app.models.feat_model import Feat  # noqa: F401

# Feature (class/subclass/race/subrace/background features and feats).
# Must come after Subclass/Subrace so the subclass_id/subrace_id FKs resolve correctly.
from app.models.feature_model import Feature  # noqa: F401

# Item and character inventory.
from app.models.item_model import Item  # noqa: F401
from app.models.race_association_models import RaceAbilityBonus, race_skills  # noqa: F401

# Race and its associations.
from app.models.race_model import Race  # noqa: F401
from app.models.skill_model import Skill  # noqa: F401

# Source-owned starting equipment (classes/backgrounds).
from app.models.source_item_model import SourceItem  # noqa: F401

# Spell.
from app.models.spell_model import Spell  # noqa: F401

# Subclass must be imported after Class (FK dependency) and before Feature (FK target).
from app.models.subclass_model import Subclass  # noqa: F401

# Subrace and its associations.
# Must come after Class/Race (FK targets) and before Feature (FK target).
from app.models.subrace_association_models import SubraceAbilityBonus  # noqa: F401
from app.models.subrace_model import Subrace  # noqa: F401
from app.models.user_model import User  # noqa: F401
from app.settings import settings  # noqa: F401
