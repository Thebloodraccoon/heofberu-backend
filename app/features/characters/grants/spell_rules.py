"""
Spell-pick rules: which spells an open ("any spell") choice option may be
picked with — the "extra empty spell slot" of Magical Secrets and the like.

A picked spell must pass the option's filter (``FeatureSpellGrantEffect``:
class lists, level range, "castable", schools, ritual) and be new to the
character: not a known spell, not a GM grant, and not given by another grant
or by this grant's own fixed effects and other picks. Picks of one request are
judged in the feature's group order, each taken spell counting for the next.

"Castable" is judged by the character's spell slots: a cantrip, or a level
the character has at least one slot of (the class progression keeps those
totals in sync with the level).

These checks run when a pick is written; on read a stale pick (the GM
narrowed the filter later, the character lost a level) still gives its spell.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.constants import SpellLevel, SpellSchool
from app.features.characters.grants.effects import GrantEffects
from app.models.features.feature_engine_models import FeatureChoiceOption, FeatureSpellGrantEffect

_LEVELS: tuple[SpellLevel, ...] = tuple(SpellLevel)


@dataclass(frozen=True)
class SpellFacts:
    """What the rules need of a catalog spell. ``class_ids`` empty = on every class list (unrestricted)."""

    id: int
    name: str
    level: SpellLevel
    school: SpellSchool
    is_ritual: bool
    class_ids: frozenset[int]


@dataclass
class SpellOwnership:
    """The character's side of a pick: the slot levels it has and every spell it already has."""

    castable_levels: set[SpellLevel]
    owned: set[int]


@dataclass
class SpellSources:
    """A character's slot levels and spells from every source, loaded once per request."""

    castable_levels: set[SpellLevel]
    row_spell_ids: set[int]
    grant_spell_ids: dict[int, set[int]]

    def ownership(self, grant_id: int, own_spell_ids: Iterable[int]) -> SpellOwnership:
        """The ownership for a pick on ``grant_id``, whose own current contribution is ``own_spell_ids``."""

        owned = {*self.row_spell_ids, *own_spell_ids}
        for other_id, spell_ids in self.grant_spell_ids.items():
            if other_id != grant_id:
                owned.update(spell_ids)
        return SpellOwnership(castable_levels=set(self.castable_levels), owned=owned)


def open_spell_effect(option: FeatureChoiceOption) -> FeatureSpellGrantEffect | None:
    """The option's open ("any spell") effect, if it has one (an option carries at most one)."""

    return next((effect for effect in option.spell_effects if effect.spell_id is None), None)


def spell_refusal(effect: FeatureSpellGrantEffect, spell: SpellFacts, ownership: SpellOwnership) -> str | None:
    """Why ``spell`` can't fill the open ``effect`` (``None`` = it can)."""

    level = _LEVELS.index(spell.level)

    if effect.class_ids and spell.class_ids and spell.class_ids.isdisjoint(effect.class_ids):
        return "it isn't on the class lists the option allows"
    if effect.min_level is not None and level < _LEVELS.index(effect.min_level):
        return "its level is below the option's range"
    if effect.max_level is not None and level > _LEVELS.index(effect.max_level):
        return "its level is above the option's range"
    if effect.castable_only and spell.level != SpellLevel.CANTRIP and spell.level not in ownership.castable_levels:
        return "the character has no spell slots of its level"
    if effect.schools and spell.school not in effect.schools:
        return "its school isn't one the option allows"
    if effect.ritual_only and not spell.is_ritual:
        return "it isn't a ritual"
    if spell.id in ownership.owned:
        return "the character already has it"
    return None


def allowed_spells(
    option: FeatureChoiceOption, candidates: Iterable[SpellFacts], ownership: SpellOwnership
) -> list[SpellFacts]:
    """The candidates the option's open effect may be picked with, by level then name (``[]`` if it isn't open)."""

    effect = open_spell_effect(option)
    if effect is None:
        return []

    fitting = (spell for spell in candidates if spell_refusal(effect, spell, ownership) is None)
    return sorted(fitting, key=lambda spell: (_LEVELS.index(spell.level), spell.name))


def build_spell_sources(
    castable_levels: Iterable[SpellLevel], row_spell_ids: Iterable[int], grants: dict[int, tuple[object, GrantEffects]]
) -> SpellSources:
    """The character's slot levels, known/GM-granted spells and every grant's spells."""

    return SpellSources(
        castable_levels=set(castable_levels),
        row_spell_ids=set(row_spell_ids),
        grant_spell_ids={grant_id: set(effects.spells) for grant_id, (_, effects) in grants.items()},
    )
