"""Unit tests for the skill-pick rules (``characters/grants/skill_rules.py``): the baseline a pick is judged against."""

from types import SimpleNamespace

import pytest

from app.constants import FeatureSourceType, ProficiencySourceType, ProficiencyType, SkillEffectMode
from app.features.characters.grants.effects import GrantEffects, SkillClaim
from app.features.characters.grants.skill_rules import build_skill_sources, pick_refusal


def skill_row(skill_id, *, is_expertise=False) -> SimpleNamespace:
    return SimpleNamespace(
        proficiency_type=ProficiencyType.SKILL,
        skill_id=skill_id,
        source_type=ProficiencySourceType.CLASS_CHOICE,
        actor_user_id=None,
        is_expertise=is_expertise,
        action=None,
        ability=None,
        armor_type=None,
        item_id=None,
        weapon_category=None,
    )


def feature(feature_id) -> SimpleNamespace:
    return SimpleNamespace(id=feature_id, name=f"Feature {feature_id}", source_type=FeatureSourceType.OTHER)


def skills(claims: dict[int, SkillClaim]) -> GrantEffects:
    return GrantEffects(skills=claims)


@pytest.mark.unit
class TestBuildSkillSourcesBaseline:
    def test_stored_rows_and_other_grants_form_the_baseline(self):
        sources = build_skill_sources(
            [skill_row(1)],
            {11: (feature(11), skills({2: SkillClaim(proficiency=True)}))},
        )

        assert sources.baseline(10, feature(10), GrantEffects()) == {1: False, 2: False}

    def test_the_picking_grant_is_judged_by_its_current_effects_not_its_stored_ones(self):
        sources = build_skill_sources([], {10: (feature(10), skills({3: SkillClaim(proficiency=True)}))})

        assert sources.baseline(10, feature(10), GrantEffects()) == {}
        assert sources.baseline(10, feature(10), skills({4: SkillClaim(proficiency=True)})) == {4: False}

    def test_another_grants_expertise_upgrades_a_stored_proficiency(self):
        sources = build_skill_sources(
            [skill_row(1)],
            {11: (feature(11), skills({1: SkillClaim(proficiency=True, expertise=True)}))},
        )

        assert sources.baseline(10, feature(10), GrantEffects()) == {1: True}

    def test_an_expertise_only_claim_without_proficiency_gives_nothing(self):
        sources = build_skill_sources([], {11: (feature(11), skills({5: SkillClaim(expertise=True)}))})

        assert 5 not in sources.baseline(10, feature(10), GrantEffects())

    def test_a_stored_expert_row_is_kept_as_expertise(self):
        sources = build_skill_sources([skill_row(6, is_expertise=True)], {})

        assert sources.baseline(10, feature(10), GrantEffects()) == {6: True}


@pytest.mark.unit
class TestPickRefusal:
    @pytest.mark.parametrize(
        ("mode", "skill_id", "baseline", "expected"),
        [
            (SkillEffectMode.PROFICIENCY, 1, {1: False}, "the character is already proficient in it"),
            (SkillEffectMode.EXPERTISE, 2, {1: False}, "expertise needs proficiency in the skill from another source"),
            (SkillEffectMode.EXPERTISE, 1, {1: True}, "the character already has expertise in it"),
            (SkillEffectMode.PROFICIENCY_AND_EXPERTISE, 1, {1: True}, "the character already has expertise in it"),
        ],
    )
    def test_refusals_against_the_baseline(self, mode, skill_id, baseline, expected):
        assert pick_refusal(mode, skill_id, baseline) == expected

    def test_a_fitting_pick_is_allowed(self):
        assert pick_refusal(SkillEffectMode.EXPERTISE, 1, {1: False}) is None
        assert pick_refusal(SkillEffectMode.PROFICIENCY, 2, {1: False}) is None
