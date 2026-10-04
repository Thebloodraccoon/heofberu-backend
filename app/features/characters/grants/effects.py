"""
Feature/feat grant effects, computed on read.

A grant's effects are its feature's fixed effect rows plus the effect
bundles of the options the player picked for the feature's choice groups
(``character_feature_choices``). Nothing is persisted per character: every
read derives them from the current effect tree, so a GM edit to a feature
(or a player's re-answer) is visible on the next read without touching
any character row.

Ability effects are collected for display only (``GrantEffects.abilities``):
the totals still come from the ability-score calculator
(``CharacterStatsRepository.get_feature_increases_many``) and its cache row.
Open ("any skill"/"any spell") effects contribute nothing, since picking one
isn't supported (``FeatureGrantService.answer_choices`` rejects it).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterWeaponProficiencyResponse,
    ChosenOptionResponse,
    GrantedAbilityEffectResponse,
    GrantedSkillEffectResponse,
)
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.features.feature_engine_models import (
    EFFECT_TYPES,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    effect_groups,
)
from app.models.features.feature_model import Feature
from app.models.spells.spell_model import Spell

_EFFECT_ATTRS = tuple(attr for _, attr in EFFECT_TYPES)


def choice_option_effect_loads(base_loader) -> list:
    """Chain the six effect-type loads of a ``FeatureChoiceOption`` onto ``base_loader``."""

    return [base_loader.selectinload(getattr(FeatureChoiceOption, attr)) for attr in _EFFECT_ATTRS]


_CHOICES_LOADER = selectinload(CharacterFeature.choices).selectinload(CharacterFeatureChoice.choice_option)

# A grant's stored picks with each picked option's six effect bundles.
GRANT_CHOICES_LOADS = (_CHOICES_LOADER, *choice_option_effect_loads(_CHOICES_LOADER))


def engine_effect_loads() -> list:
    """Eager loads for a feature's whole effect tree: fixed effects plus every choice option's bundle."""

    options_loader = selectinload(Feature.choice_groups).selectinload(FeatureChoiceGroup.options)
    return [selectinload(getattr(Feature, attr)) for attr in _EFFECT_ATTRS] + choice_option_effect_loads(options_loader)


async def load_feature_effect_tree(db: AsyncSession, feature_id: int) -> Feature | None:
    """Fetch a feature with its full effect tree, or ``None`` if it doesn't exist."""

    result = await db.execute(select(Feature).where(Feature.id == feature_id).options(*engine_effect_loads()))
    return result.scalars().first()


async def load_feature_effect_trees(db: AsyncSession, feature_ids: Iterable[int]) -> dict[int, Feature]:
    """Batched ``load_feature_effect_tree``; missing ids are absent from the result."""

    ids = set(feature_ids)
    if not ids:
        return {}

    result = await db.execute(select(Feature).where(Feature.id.in_(ids)).options(*engine_effect_loads()))
    return {feature.id: feature for feature in result.scalars().unique().all()}


@dataclass
class GrantEffects:
    """
    What one grant gives the character: skill id -> expertise, the other
    proficiency keys and spell ids, plus its ability effects (display only).
    """

    abilities: list[tuple] = field(default_factory=list)
    skills: dict[int, bool] = field(default_factory=dict)
    saving_throws: set = field(default_factory=set)
    armor: set = field(default_factory=set)
    weapons: set[tuple] = field(default_factory=set)
    spells: set[int] = field(default_factory=set)

    def add(self, holder: Feature | FeatureChoiceOption) -> None:
        """Fold one effect bundle (a feature's fixed rows or a picked option's rows) in."""

        self.abilities.extend((effect.ability, effect.amount, effect.new_cap) for effect in holder.ability_effects)
        for effect in holder.skill_effects:
            if effect.skill_id is not None:
                self.skills[effect.skill_id] = self.skills.get(effect.skill_id, False) or bool(effect.grants_expertise)

        self.saving_throws.update(effect.ability for effect in holder.saving_throw_effects)
        self.armor.update(effect.armor_type for effect in holder.armor_effects)
        self.weapons.update((effect.weapon_category, effect.item_id) for effect in holder.weapon_effects)
        self.spells.update(effect.spell_id for effect in holder.spell_effects if effect.spell_id is not None)


def grant_effects(feature: Feature, picked_option_ids: Iterable[int]) -> GrantEffects:
    """Effects of a grant of ``feature`` whose player picked ``picked_option_ids`` (unknown ids are ignored)."""

    effects = GrantEffects()
    effects.add(feature)

    options = {option.id: option for group in feature.choice_groups for option in group.options}
    for option_id in picked_option_ids:
        option = options.get(option_id)
        if option is not None:
            effects.add(option)

    return effects


def pending_groups(feature: Feature, stored_choices: list[CharacterFeatureChoice]) -> list[FeatureChoiceGroup]:
    """The feature's choice groups that still need picks (stored count < ``pick_count``)."""

    picked_counts: dict[int, int] = defaultdict(int)
    for choice in stored_choices:
        picked_counts[choice.choice_group_id] += 1

    return [group for group in feature.choice_groups if picked_counts[group.id] < group.pick_count]


async def load_grant_effects(
    db: AsyncSession, grants: list[CharacterFeature]
) -> dict[int, tuple[Feature, GrantEffects]]:
    """
    ``{grant_id: (feature, effects)}`` for every grant whose feature still
    exists — one batched effect-tree load plus one query for every grant's
    stored picks.
    """

    if not grants:
        return {}

    features = await load_feature_effect_trees(db, (grant.feature_id for grant in grants))

    picks: dict[int, list[int]] = defaultdict(list)
    result = await db.execute(
        select(CharacterFeatureChoice.character_feature_id, CharacterFeatureChoice.choice_option_id).where(
            CharacterFeatureChoice.character_feature_id.in_([grant.id for grant in grants])
        )
    )
    for grant_id, option_id in result.all():
        picks[grant_id].append(option_id)

    return {
        grant.id: (feature, grant_effects(feature, picks[grant.id]))
        for grant in grants
        if (feature := features.get(grant.feature_id)) is not None
    }


async def load_character_grant_effects(db: AsyncSession, character_id: int) -> list[tuple[Feature, GrantEffects]]:
    """
    ``(feature, effects)`` for every feature/feat grant of the character that
    can give anything — features with neither fixed effects nor choice groups
    (``has_static_effects``/``has_choices``) are skipped without loading
    their tree.
    """

    result = await db.execute(
        select(CharacterFeature)
        .join(Feature, Feature.id == CharacterFeature.feature_id)
        .where(
            CharacterFeature.character_id == character_id,
            or_(Feature.has_static_effects.is_(True), Feature.has_choices.is_(True)),
        )
    )
    by_grant = await load_grant_effects(db, list(result.scalars().all()))
    return list(by_grant.values())


async def load_spell_responses(db: AsyncSession, spell_ids: Iterable[int]) -> dict[int, CharacterSpellResponse]:
    """``{spell_id: CharacterSpellResponse}`` for the given ids (one plain query, no availability loads)."""

    ids = set(spell_ids)
    if not ids:
        return {}

    result = await db.execute(select(Spell).where(Spell.id.in_(ids)))
    return {spell.id: CharacterSpellResponse.model_validate(spell) for spell in result.scalars().unique().all()}


def spell_list(spell_ids: Iterable[int], spells: dict[int, CharacterSpellResponse]) -> list[CharacterSpellResponse]:
    """The given spells (deduplicated, missing ids skipped), ordered by name."""

    return sorted((spells[spell_id] for spell_id in set(spell_ids) if spell_id in spells), key=lambda spell: spell.name)


def _weapon_sort_key(weapon: tuple) -> tuple:
    """Stable order for ``(weapon_category, item_id)`` pairs, either part possibly ``None``."""

    category, item_id = weapon
    return (category is None, getattr(category, "value", category) or "", item_id is None, item_id or 0)


def _to_response(effects: GrantEffects, spells: dict[int, CharacterSpellResponse]) -> list[dict]:
    """Serialize one grant's computed effects as non-empty ``GrantEffectGroup`` entries, in ``EFFECT_TYPES`` order."""

    items_by_type: dict[str, list] = {
        "ability": [
            GrantedAbilityEffectResponse(ability=ability, amount=amount, new_cap=new_cap)
            for ability, amount, new_cap in effects.abilities
        ],
        "skill": [
            GrantedSkillEffectResponse(skill_id=skill_id, is_expertise=expertise)
            for skill_id, expertise in sorted(effects.skills.items())
        ],
        "saving_throw": [
            CharacterSavingThrowProficiencyResponse(ability=ability) for ability in sorted(effects.saving_throws)
        ],
        "armor": [CharacterArmorProficiencyResponse(armor_type=armor_type) for armor_type in sorted(effects.armor)],
        "weapon": [
            CharacterWeaponProficiencyResponse(weapon_category=category, item_id=item_id)
            for category, item_id in sorted(effects.weapons, key=_weapon_sort_key)
        ],
        "spell": spell_list(effects.spells, spells),
    }
    return [
        {"effect_type": effect_type, "items": items_by_type[effect_type]}
        for effect_type, _ in EFFECT_TYPES
        if items_by_type[effect_type]
    ]


async def get_grant_effects_map(db: AsyncSession, grants: list[CharacterFeature]) -> dict[int, list[dict]]:
    """
    ``{grant_id: [GrantEffectGroup, ...]}`` for listing endpoints. Computes from
    the trees the caller already loaded: each grant needs ``feature`` (with
    its full effect tree — see ``feature_summary_loads``) and ``choices``
    (see ``GRANT_CHOICES_LOADS``) eager-loaded, so the only query here is
    the spell lookup.
    """

    effects_by_grant = {
        grant.id: grant_effects(grant.feature, (choice.choice_option_id for choice in grant.choices))
        for grant in grants
    }
    spells = await load_spell_responses(
        db, (spell_id for effects in effects_by_grant.values() for spell_id in effects.spells)
    )

    return {grant_id: _to_response(effects, spells) for grant_id, effects in effects_by_grant.items()}


def build_chosen_options(grant: CharacterFeature) -> list[ChosenOptionResponse]:
    """
    The player's picks for a grant, from its stored ``CharacterFeatureChoice``
    rows. Requires ``grant.choices`` (and each choice's ``choice_option`` with
    its six effect relationships) eager-loaded — see ``choice_option_effect_loads``.
    """

    return [
        ChosenOptionResponse.model_validate(
            {
                "choice_group_id": choice.choice_group_id,
                "choice_option_id": choice.choice_option_id,
                "effects": effect_groups(choice.choice_option) if choice.choice_option is not None else [],
            },
            from_attributes=True,
        )
        for choice in grant.choices
    ]
