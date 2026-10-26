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

A skill effect gives what its ``mode`` says, folded per skill into a
:class:`SkillClaim`; whether an ``EXPERTISE``/``UPGRADE`` claim actually
yields expertise depends on the character's other sources and is decided
by the proficiency resolver. An open ("any skill") effect applies to the
skill the player named for the pick (``CharacterFeatureChoice.picked_skill_id``),
an open ("any spell") effect gives the spell named for it (``picked_spell_id``),
an open ability-score / saving-throw effect the ability named for it (``picked_ability``),
an open ("any tool") effect the tool named for it (``picked_item_id``).

Speed and AC effect rows are collected as they are (``GrantEffects.speeds`` /
``armor_class``): what they amount to depends on the character's equipment
and level, decided by ``characters.combat``.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import AbilityScore, SkillEffectMode
from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterToolProficiencyResponse,
    CharacterWeaponProficiencyResponse,
    ChosenOptionResponse,
    GrantedAbilityEffectResponse,
    GrantedSkillEffectResponse,
)
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.features.feature_engine_models import (
    CHOICE_OPTION_EFFECT_ATTRS,
    EFFECT_TYPES,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSpellGrantEffect,
    effect_groups,
)
from app.models.features.feature_model import Feature
from app.models.spells.spell_model import Spell

_EFFECT_ATTRS = tuple(attr for _, attr in EFFECT_TYPES)


def choice_option_effect_loads(base_loader, *, with_spell_filters: bool = False) -> list:
    """
    Chain the effect-type loads of a ``FeatureChoiceOption`` onto ``base_loader``; with
    ``with_spell_filters`` spell rows also load their filter's classes (for ``summary`` in responses).
    """

    loads = [base_loader.selectinload(getattr(FeatureChoiceOption, attr)) for attr in CHOICE_OPTION_EFFECT_ATTRS]
    if with_spell_filters:
        loads.append(
            base_loader.selectinload(FeatureChoiceOption.spell_effects).selectinload(
                FeatureSpellGrantEffect.filter_classes
            )
        )
    return loads


_CHOICES_LOADER = selectinload(CharacterFeature.choices).selectinload(CharacterFeatureChoice.choice_option)

# A grant's stored picks with each picked option's effect bundles.
GRANT_CHOICES_LOADS = (_CHOICES_LOADER, *choice_option_effect_loads(_CHOICES_LOADER, with_spell_filters=True))


def engine_effect_loads(*, with_spell_filters: bool = False) -> list:
    """
    Eager loads for a feature's whole effect tree: fixed effects plus every choice option's bundle
    (``with_spell_filters``: see :func:`choice_option_effect_loads` — only the choices surface needs it).
    """

    options_loader = selectinload(Feature.choice_groups).selectinload(FeatureChoiceGroup.options)
    return [selectinload(getattr(Feature, attr)) for attr in _EFFECT_ATTRS] + choice_option_effect_loads(
        options_loader, with_spell_filters=with_spell_filters
    )


async def load_feature_effect_tree(db: AsyncSession, feature_id: int) -> Feature | None:
    """Fetch a feature with its full effect tree, or ``None`` if it doesn't exist."""

    result = await db.execute(select(Feature).where(Feature.id == feature_id).options(*engine_effect_loads()))
    return result.scalars().first()


async def load_feature_effect_trees(
    db: AsyncSession, feature_ids: Iterable[int], *, with_spell_filters: bool = False
) -> dict[int, Feature]:
    """Batched ``load_feature_effect_tree``; missing ids are absent from the result."""

    ids = set(feature_ids)
    if not ids:
        return {}

    loads = engine_effect_loads(with_spell_filters=with_spell_filters)
    result = await db.execute(select(Feature).where(Feature.id.in_(ids)).options(*loads))
    return {feature.id: feature for feature in result.scalars().unique().all()}


@dataclass
class SkillClaim:
    """
    What one grant's skill effects give in ONE skill, folded across its
    effects: ``proficiency`` (PROFICIENCY / PROFICIENCY_AND_EXPERTISE),
    ``expertise`` (PROFICIENCY_AND_EXPERTISE / EXPERTISE) and ``upgrade``
    (UPGRADE — proficiency, or expertise when another source gives the
    proficiency).
    """

    proficiency: bool = False
    expertise: bool = False
    upgrade: bool = False

    def add(self, mode: SkillEffectMode) -> None:
        """Fold one effect's ``mode`` in."""

        self.proficiency |= mode in (SkillEffectMode.PROFICIENCY, SkillEffectMode.PROFICIENCY_AND_EXPERTISE)
        self.expertise |= mode in (SkillEffectMode.PROFICIENCY_AND_EXPERTISE, SkillEffectMode.EXPERTISE)
        self.upgrade |= mode == SkillEffectMode.UPGRADE

    @property
    def grants(self) -> bool:
        """Whether the claim gives the proficiency itself (an EXPERTISE-only claim does not)."""

        return self.proficiency or self.upgrade

    @property
    def is_expertise(self) -> bool:
        """Expertise this grant gives on its own (an UPGRADE counts when the same grant also gives the proficiency)."""

        return self.expertise or (self.upgrade and self.proficiency)

    @property
    def mode(self) -> SkillEffectMode:
        """The one mode the folded claim amounts to (for responses)."""

        if self.grants and self.is_expertise:
            return SkillEffectMode.PROFICIENCY_AND_EXPERTISE
        if self.upgrade:
            return SkillEffectMode.UPGRADE
        if self.proficiency:
            return SkillEffectMode.PROFICIENCY
        return SkillEffectMode.EXPERTISE


@dataclass
class GrantEffects:
    """
    What one grant gives the character: a :class:`SkillClaim` per skill id,
    the other proficiency keys and spell ids, its ability effects (display
    only) and its speed / AC effect rows (resolved by ``characters.combat``).
    """

    abilities: list[tuple] = field(default_factory=list)
    skills: dict[int, SkillClaim] = field(default_factory=dict)
    saving_throws: set = field(default_factory=set)
    armor: set[tuple] = field(default_factory=set)
    weapons: set[tuple] = field(default_factory=set)
    tools: set[int] = field(default_factory=set)
    spells: set[int] = field(default_factory=set)
    speeds: list[Any] = field(default_factory=list)
    armor_class: list[Any] = field(default_factory=list)

    def add(
        self,
        holder: Feature | FeatureChoiceOption,
        picked_skill_id: int | None = None,
        picked_spell_id: int | None = None,
        picked_ability: AbilityScore | None = None,
        picked_item_id: int | None = None,
    ) -> None:
        """
        Fold one effect bundle (a feature's fixed rows or a picked option's rows) in. An open effect gives
        what was named for the pick (``picked_skill_id``/``picked_spell_id``/``picked_ability``/
        ``picked_item_id``); without one it gives nothing.
        """

        for effect in holder.ability_effects:
            ability = effect.ability if effect.ability is not None else picked_ability
            if ability is not None:
                self.abilities.append((ability, effect.amount, effect.new_cap))
        for skill_effect in holder.skill_effects:
            skill_id = skill_effect.skill_id if skill_effect.skill_id is not None else picked_skill_id
            if skill_id is not None:
                self.skills.setdefault(skill_id, SkillClaim()).add(skill_effect.mode)

        for save_effect in holder.saving_throw_effects:
            ability = save_effect.ability if save_effect.ability is not None else picked_ability
            if ability is not None:
                self.saving_throws.add(ability)
        self.armor.update((effect.armor_type, effect.item_id) for effect in holder.armor_effects)
        self.weapons.update((effect.weapon_category, effect.item_id) for effect in holder.weapon_effects)
        for tool_effect in holder.tool_effects:
            item_id = tool_effect.item_id if tool_effect.item_id is not None else picked_item_id
            if item_id is not None:
                self.tools.add(item_id)
        for spell_effect in holder.spell_effects:
            spell_id = spell_effect.spell_id if spell_effect.spell_id is not None else picked_spell_id
            if spell_id is not None:
                self.spells.add(spell_id)
        self.speeds.extend(holder.speed_effects)
        self.armor_class.extend(holder.armor_class_effects)


# One stored pick as ``grant_effects`` reads it:
# ``(choice_option_id, picked_skill_id, picked_spell_id, picked_ability, picked_item_id)``.
Pick = tuple[int, int | None, int | None, AbilityScore | None, int | None]


def grant_effects(feature: Feature, picks: Iterable[Pick]) -> GrantEffects:
    """Effects of a grant of ``feature`` whose player made ``picks`` (unknown option ids are ignored)."""

    effects = GrantEffects()
    effects.add(feature)

    options = {option.id: option for group in feature.choice_groups for option in group.options}
    for option_id, skill_id, spell_id, ability, item_id in picks:
        option = options.get(option_id)
        if option is not None:
            effects.add(option, skill_id, spell_id, ability, item_id)

    return effects


def stored_picks(choices: Iterable[CharacterFeatureChoice]) -> list[Pick]:
    """``grant_effects`` input from stored pick rows."""

    return [
        (
            choice.choice_option_id,
            choice.picked_skill_id,
            choice.picked_spell_id,
            choice.picked_ability,
            choice.picked_item_id,
        )
        for choice in choices
    ]


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

    picks: dict[int, list[Pick]] = defaultdict(list)
    result = await db.execute(
        select(
            CharacterFeatureChoice.character_feature_id,
            CharacterFeatureChoice.choice_option_id,
            CharacterFeatureChoice.picked_skill_id,
            CharacterFeatureChoice.picked_spell_id,
            CharacterFeatureChoice.picked_ability,
            CharacterFeatureChoice.picked_item_id,
        ).where(CharacterFeatureChoice.character_feature_id.in_([grant.id for grant in grants]))
    )
    for grant_id, *pick in result.all():
        picks[grant_id].append(tuple(pick))

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

    return list((await load_character_grant_effects_by_grant(db, character_id)).values())


async def load_character_grant_effects_by_grant(
    db: AsyncSession, character_id: int
) -> dict[int, tuple[Feature, GrantEffects]]:
    """:func:`load_character_grant_effects` keyed by grant id (to leave one grant out of a computation)."""

    result = await db.execute(
        select(CharacterFeature)
        .join(Feature, Feature.id == CharacterFeature.feature_id)
        .where(
            CharacterFeature.character_id == character_id,
            or_(Feature.has_static_effects.is_(True), Feature.has_choices.is_(True)),
        )
    )
    return await load_grant_effects(db, list(result.scalars().all()))


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


def _target_sort_key(target: tuple) -> tuple:
    """Stable order for ``(category, item_id)`` pairs (weapons, armor), either part possibly ``None``."""

    category, item_id = target
    return (category is None, getattr(category, "value", category) or "", item_id is None, item_id or 0)


def _to_response(effects: GrantEffects, spells: dict[int, CharacterSpellResponse]) -> list[Any]:
    """Serialize one grant's computed effects as non-empty ``GrantEffectGroup`` entries, in ``EFFECT_TYPES`` order."""

    items_by_type: dict[str, list] = {
        "ability": [
            GrantedAbilityEffectResponse(ability=ability, amount=amount, new_cap=new_cap)
            for ability, amount, new_cap in effects.abilities
        ],
        "skill": [
            GrantedSkillEffectResponse(skill_id=skill_id, is_expertise=claim.is_expertise, mode=claim.mode)
            for skill_id, claim in sorted(effects.skills.items())
        ],
        "saving_throw": [
            CharacterSavingThrowProficiencyResponse(ability=ability) for ability in sorted(effects.saving_throws)
        ],
        "armor": [
            CharacterArmorProficiencyResponse(armor_type=armor_type, item_id=item_id)
            for armor_type, item_id in sorted(effects.armor, key=_target_sort_key)
        ],
        "weapon": [
            CharacterWeaponProficiencyResponse(weapon_category=category, item_id=item_id)
            for category, item_id in sorted(effects.weapons, key=_target_sort_key)
        ],
        "tool": [CharacterToolProficiencyResponse(item_id=item_id) for item_id in sorted(effects.tools)],
        "spell": spell_list(effects.spells, spells),
        "speed": effects.speeds,
        "armor_class": effects.armor_class,
    }
    return [
        {"effect_type": effect_type, "items": items_by_type[effect_type]}
        for effect_type, _ in EFFECT_TYPES
        if items_by_type[effect_type]
    ]


async def get_grant_effects_map(db: AsyncSession, grants: list[CharacterFeature]) -> dict[int, list[Any]]:
    """
    ``{grant_id: [GrantEffectGroup, ...]}`` for listing endpoints. Computes from
    the trees the caller already loaded: each grant needs ``feature`` (with
    its full effect tree — see ``feature_summary_loads``) and ``choices``
    (see ``GRANT_CHOICES_LOADS``) eager-loaded, so the only query here is
    the spell lookup.
    """

    effects_by_grant = {grant.id: grant_effects(grant.feature, stored_picks(grant.choices)) for grant in grants}
    spells = await load_spell_responses(
        db, (spell_id for effects in effects_by_grant.values() for spell_id in effects.spells)
    )

    return {grant_id: _to_response(effects, spells) for grant_id, effects in effects_by_grant.items()}


def build_chosen_options(grant: CharacterFeature) -> list[ChosenOptionResponse]:
    """
    The player's picks for a grant, from its stored ``CharacterFeatureChoice``
    rows. Requires ``grant.choices`` (and each choice's ``choice_option`` with
    its effect relationships) eager-loaded — see ``choice_option_effect_loads``.
    """

    return [
        ChosenOptionResponse.model_validate(
            {
                "choice_group_id": choice.choice_group_id,
                "choice_option_id": choice.choice_option_id,
                "picked_skill_id": choice.picked_skill_id,
                "picked_spell_id": choice.picked_spell_id,
                "picked_ability": choice.picked_ability,
                "picked_item_id": choice.picked_item_id,
                "effects": effect_groups(choice.choice_option) if choice.choice_option is not None else [],
            },
            from_attributes=True,
        )
        for choice in grant.choices
    ]
