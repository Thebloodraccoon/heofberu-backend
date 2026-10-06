"""Unit tests for the pure feat validators (cap, prerequisite, min level, required ASI pick)."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.feats.exceptions import (
    AbilityScoreCapExceededException,
    FeatAsiChoiceRequiredException,
    FeatMinLevelNotMetException,
    FeatPrerequisiteNotMetException,
)
from app.features.characters.feats.validation import (
    ensure_feat_asi_within_cap,
    ensure_feat_min_level,
    ensure_prerequisite_met,
    ensure_within_cap,
    validate_asi_choice_required,
)
from tests.unit.features.characters.conftest import make_feat_with_choice_groups

TOTALS = {
    "strength_total": 19,
    "dexterity_total": 10,
    "constitution_total": 12,
    "intelligence_total": 8,
    "wisdom_total": 9,
    "charisma_total": 11,
}


@pytest.mark.unit
class TestEnsureWithinCap:
    def test_reaching_twenty_is_allowed(self):
        ensure_within_cap(TOTALS, AbilityScore.STR, 1)

    def test_going_over_twenty_reports_current_and_requested(self):
        with pytest.raises(AbilityScoreCapExceededException) as exc_info:
            ensure_within_cap(TOTALS, AbilityScore.STR, 2)

        assert (exc_info.value.current_total, exc_info.value.requested) == (19, 21)
        assert exc_info.value.status_code == 400


@pytest.mark.unit
class TestEnsureFeatAsiWithinCap:
    def test_selected_option_over_the_cap_is_rejected(self):
        feat = make_feat_with_choice_groups([(AbilityScore.STR, 2)])

        with pytest.raises(AbilityScoreCapExceededException):
            ensure_feat_asi_within_cap(feat, 200, TOTALS)

    def test_option_within_the_cap_passes(self):
        feat = make_feat_with_choice_groups([(AbilityScore.DEX, 2)])

        ensure_feat_asi_within_cap(feat, 200, TOTALS)

    def test_no_pick_or_unknown_pick_is_a_noop(self):
        feat = make_feat_with_choice_groups([(AbilityScore.STR, 2)])

        ensure_feat_asi_within_cap(feat, None, TOTALS)
        ensure_feat_asi_within_cap(feat, 999, TOTALS)


@pytest.mark.unit
class TestEnsurePrerequisiteMet:
    def test_no_prerequisite_passes(self):
        ensure_prerequisite_met(make_feat_with_choice_groups(), TOTALS)

    def test_met_prerequisite_passes(self):
        feat = make_feat_with_choice_groups(prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=19)

        ensure_prerequisite_met(feat, TOTALS)

    def test_unmet_prerequisite_reports_actual_score(self):
        feat = make_feat_with_choice_groups(prerequisite_ability=AbilityScore.DEX, prerequisite_minimum_score=13)

        with pytest.raises(FeatPrerequisiteNotMetException) as exc_info:
            ensure_prerequisite_met(feat, TOTALS)

        assert (exc_info.value.required_minimum, exc_info.value.actual) == (13, 10)


@pytest.mark.unit
class TestEnsureFeatMinLevel:
    def test_no_min_level_passes(self):
        ensure_feat_min_level(SimpleNamespace(id=1, min_level=None), 1)

    def test_level_at_or_above_min_level_passes(self):
        ensure_feat_min_level(SimpleNamespace(id=1, min_level=8), 8)
        ensure_feat_min_level(SimpleNamespace(id=1, min_level=8), 12)

    def test_level_below_min_level_is_rejected(self):
        with pytest.raises(FeatMinLevelNotMetException) as exc_info:
            ensure_feat_min_level(SimpleNamespace(id=1, min_level=8), 4)

        assert exc_info.value.status_code == 400
        assert (exc_info.value.min_level, exc_info.value.level) == (8, 4)


@pytest.mark.unit
class TestValidateAsiChoiceRequired:
    def test_feat_with_options_needs_a_pick(self):
        feat = make_feat_with_choice_groups([(AbilityScore.STR, 1)])

        with pytest.raises(FeatAsiChoiceRequiredException):
            validate_asi_choice_required(feat, None)

        validate_asi_choice_required(feat, 200)

    def test_feat_without_options_needs_nothing(self):
        validate_asi_choice_required(make_feat_with_choice_groups(), None)
