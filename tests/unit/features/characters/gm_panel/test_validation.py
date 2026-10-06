"""Unit tests for the shared feat-ASI choice/prerequisite validation helpers."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.feats.exceptions import (
    FeatAsiChoiceRequiredException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.characters.feats.validation import (
    check_feat_prerequisite,
    validate_ability_score_increase,
    validate_asi_choice_required,
)
from tests.unit.features.characters.conftest import make_feat_with_choice_groups

TOTALS = {
    "strength_total": 14,
    "dexterity_total": 10,
    "constitution_total": 12,
    "intelligence_total": 8,
    "wisdom_total": 9,
    "charisma_total": 11,
}


class FakeStatsService:
    """Serves precomputed totals/caps; records compute calls."""

    def __init__(self, totals=None, caps=None):
        self.totals = totals or dict(TOTALS)
        self.caps = caps if caps is not None else dict.fromkeys(AbilityScore, 20)
        self.compute_calls = []

    async def compute(self, character):
        self.compute_calls.append(character)
        return self.totals

    async def resolve_ability_caps(self, character):
        return self.caps


def make_feat(**overrides):
    """Build a feat with choice_groups form. Pass ability_effects=[(ability, amount), ...]."""
    ability_effects = overrides.pop("ability_effects", None)
    return make_feat_with_choice_groups(ability_effects=ability_effects, **overrides)


@pytest.mark.unit
class TestValidateAbilityScoreIncrease:
    def test_accepts_an_id_from_the_feats_own_options(self):
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1), (AbilityScore.DEX, 1)])

        assert validate_ability_score_increase(feat, 201) is None

    def test_rejects_a_foreign_id(self):
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1)])

        with pytest.raises(InvalidAbilityScoreIncreaseException) as exc_info:
            validate_ability_score_increase(feat, 999)

        assert exc_info.value.status_code == 400
        assert exc_info.value.ability_score_increase_id == 999


@pytest.mark.unit
class TestValidateAsiChoiceRequired:
    def test_offering_feat_without_choice_is_rejected(self):
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1)])

        with pytest.raises(FeatAsiChoiceRequiredException) as exc_info:
            validate_asi_choice_required(feat, None)

        assert exc_info.value.status_code == 422
        assert exc_info.value.choices == 1

    def test_explicit_choice_passes_even_when_offered(self):
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1)])

        assert validate_asi_choice_required(feat, 200) is None

    def test_feat_without_options_needs_no_choice(self):
        feat = make_feat(ability_effects=[])

        assert validate_asi_choice_required(feat, None) is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestCheckFeatPrerequisite:
    async def test_no_prerequisite_passes_without_computing(self):
        feat = SimpleNamespace(id=2, choice_groups=[], prerequisite_ability=None, prerequisite_minimum_score=None)
        stats = FakeStatsService()

        assert await check_feat_prerequisite(SimpleNamespace(), feat, stats) is None
        assert stats.compute_calls == []

    async def test_partial_prerequisite_passes(self):
        feat = SimpleNamespace(
            id=2, choice_groups=[], prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=None
        )
        stats = FakeStatsService()

        assert await check_feat_prerequisite(SimpleNamespace(), feat, stats) is None
        assert stats.compute_calls == []

    async def test_met_prerequisite_passes(self):
        feat = SimpleNamespace(
            id=2, choice_groups=[], prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=14
        )
        stats = FakeStatsService()

        assert await check_feat_prerequisite(SimpleNamespace(), feat, stats) is None

    async def test_unmet_prerequisite_raises(self):
        feat = SimpleNamespace(
            id=2, choice_groups=[], prerequisite_ability=AbilityScore.INT, prerequisite_minimum_score=13
        )
        stats = FakeStatsService(totals={**TOTALS, "intelligence_total": 8})

        with pytest.raises(FeatPrerequisiteNotMetException) as exc_info:
            await check_feat_prerequisite(SimpleNamespace(), feat, stats)

        assert exc_info.value.ability == "INT"
        assert exc_info.value.required_minimum == 13
        assert exc_info.value.actual == 8

    async def test_check_uses_effective_totals_not_base_columns(self):
        feat = SimpleNamespace(
            id=2, choice_groups=[], prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=15
        )
        character = SimpleNamespace(strength=14)
        stats = FakeStatsService(totals={**TOTALS, "strength_total": 16})

        assert await check_feat_prerequisite(character, feat, stats) is None
        assert stats.compute_calls == [character]
