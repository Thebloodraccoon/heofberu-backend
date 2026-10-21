"""
Skill-pick rules: what a SKILL choice option may be picked with, judged
against the character's OTHER sources.

The *baseline* of a pick is every skill the character resolves as proficient
(``skill_id -> is_expertise``) from its stored proficiency rows, every other
grant, and this grant's fixed effects plus its picks in the groups that are
not being (re)answered. Against it each skill effect of a picked option must
make sense:

- ``PROFICIENCY`` — not already proficient (the pick would be wasted);
- ``EXPERTISE`` — already proficient, and not already expert;
- ``PROFICIENCY_AND_EXPERTISE`` / ``UPGRADE`` — not already expert.

Picks of one request are judged in the feature's group order, each applied
to the baseline before the next, so "proficiency in any skill" followed by
"expertise in a skill you are proficient in" may name the same skill.

These checks run when a pick is written; on read a stale pick never breaks
the sheet — an ``EXPERTISE`` effect whose proficiency was lost later simply
gives nothing (see ``proficiencies.resolver``).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.constants import ProficiencyType, SkillEffectMode
from app.features.characters.grants.effects import GrantEffects
from app.features.characters.proficiencies.resolver import (
    ProficiencyEntry,
    feature_entries,
    resolve_all,
    row_entry,
)
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.features.feature_engine_models import FeatureChoiceOption
from app.models.features.feature_model import Feature

# skill_id -> is_expertise, for every skill the character is proficient in
SkillBaseline = dict[int, bool]


def _skill_entries(entries: list[ProficiencyEntry]) -> list[ProficiencyEntry]:
    return [entry for entry in entries if entry.key[0] == ProficiencyType.SKILL]


@dataclass
class SkillSources:
    """A character's skill entries from stored rows and from every grant, loaded once per request."""

    row_entries: list[ProficiencyEntry]
    grant_entries: dict[int, list[ProficiencyEntry]]

    def baseline(self, grant_id: int, feature: Feature, own_effects: GrantEffects) -> SkillBaseline:
        """The baseline for a pick on ``grant_id``, whose own current contribution is ``own_effects``."""

        entries = [*self.row_entries, *_skill_entries(feature_entries(feature, own_effects))]
        for other_id, other_entries in self.grant_entries.items():
            if other_id != grant_id:
                entries.extend(other_entries)

        return {proficiency.key[1]: proficiency.is_expertise for proficiency in resolve_all(entries)}


def build_skill_sources(
    rows: Iterable[CharacterProficiency], grants: dict[int, tuple[Feature, GrantEffects]]
) -> SkillSources:
    """The character's skill entries from its stored proficiency rows and every grant's computed effects."""

    return SkillSources(
        row_entries=_skill_entries([row_entry(row) for row in rows]),
        grant_entries={
            grant_id: _skill_entries(feature_entries(feature, effects))
            for grant_id, (feature, effects) in grants.items()
        },
    )


def pick_refusal(mode: SkillEffectMode, skill_id: int, baseline: SkillBaseline) -> str | None:
    """Why an effect of ``mode`` can't be taken for ``skill_id`` against ``baseline`` (``None`` = it can)."""

    proficient = skill_id in baseline
    expert = baseline.get(skill_id, False)

    if mode == SkillEffectMode.PROFICIENCY and proficient:
        return "the character is already proficient in it"
    if mode == SkillEffectMode.EXPERTISE and not proficient:
        return "expertise needs proficiency in the skill from another source"
    if expert:
        return "the character already has expertise in it"
    return None


def apply_pick(mode: SkillEffectMode, skill_id: int, baseline: SkillBaseline) -> None:
    """Fold an effect of ``mode`` taken for ``skill_id`` into ``baseline`` (in place)."""

    proficient = skill_id in baseline

    if mode == SkillEffectMode.PROFICIENCY:
        baseline.setdefault(skill_id, False)
    elif mode == SkillEffectMode.PROFICIENCY_AND_EXPERTISE:
        baseline[skill_id] = True
    elif mode == SkillEffectMode.EXPERTISE:
        if proficient:
            baseline[skill_id] = True
    else:  # UPGRADE
        baseline[skill_id] = proficient or baseline.get(skill_id, False)


def option_refusal(
    option: FeatureChoiceOption, picked_skill_id: int | None, baseline: SkillBaseline
) -> tuple[int, str] | None:
    """
    ``(skill_id, reason)`` for the first skill effect of ``option`` that can't be taken (an open effect for
    ``picked_skill_id``), or ``None`` when the whole option fits ``baseline``.
    """

    for effect in option.skill_effects:
        skill_id = effect.skill_id if effect.skill_id is not None else picked_skill_id
        if skill_id is None:
            continue

        reason = pick_refusal(effect.mode, skill_id, baseline)
        if reason is not None:
            return skill_id, reason

    return None


def apply_option(option: FeatureChoiceOption, picked_skill_id: int | None, baseline: SkillBaseline) -> None:
    """Fold every skill effect of a taken ``option`` into ``baseline`` (in place)."""

    for effect in option.skill_effects:
        skill_id = effect.skill_id if effect.skill_id is not None else picked_skill_id
        if skill_id is not None:
            apply_pick(effect.mode, skill_id, baseline)
