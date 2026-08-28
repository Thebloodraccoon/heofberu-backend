"""Unit tests for the shared GM-panel ASI-choice/prerequisite validation helpers."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.gm_panel.exceptions import (
    FeatAsiChoiceRequiredException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.characters.gm_panel.validation import (
    check_feat_prerequisite,
    validate_ability_score_increase,
    validate_ability_score_increase_cap,
    validate_asi_choice_required,
)
from app.features.characters.progression.exceptions import AbilityScoreCapExceededException

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


def make_increase(increase_id=10, ability=AbilityScore.STR, amount=1) -> SimpleNamespace:
    return SimpleNamespace(id=increase_id, feat_id=2, ability=ability, amount=amount)


@pytest.mark.unit
class TestValidateAbilityScoreIncrease:
    def test_accepts_an_id_from_the_feats_own_options(self):
        feat = SimpleNamespace(id=2, ability_score_increases=[make_increase(10), make_increase(11)])

        assert validate_ability_score_increase(feat, 11) is None

    def test_rejects_a_foreign_id(self):
        feat = SimpleNamespace(id=2, ability_score_increases=[make_increase(10)])

        with pytest.raises(InvalidAbilityScoreIncreaseException) as exc_info:
            validate_ability_score_increase(feat, 99)

        assert exc_info.value.status_code == 400
        assert exc_info.value.ability_score_increase_id == 99


@pytest.mark.unit
class TestValidateAsiChoiceRequired:
    def test_offering_feat_without_choice_is_rejected(self):
        feat = SimpleNamespace(id=2, ability_score_increases=[make_increase(10)])

        with pytest.raises(FeatAsiChoiceRequiredException) as exc_info:
            validate_asi_choice_required(feat, None)

        assert exc_info.value.status_code == 422
        assert exc_info.value.choices == 1

    def test_explicit_choice_passes_even_when_offered(self):
        feat = SimpleNamespace(id=2, ability_score_increases=[make_increase(10)])

        assert validate_asi_choice_required(feat, 10) is None

    def test_feat_without_options_needs_no_choice(self):
        feat = SimpleNamespace(id=2, ability_score_increases=[])

        assert validate_asi_choice_required(feat, None) is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestValidateAbilityScoreIncreaseCap:
    async def test_unknown_increase_is_a_no_op(self):
        feat = SimpleNamespace(id=2, ability_score_increases=[make_increase(10)])
        stats = FakeStatsService()

        assert await validate_ability_score_increase_cap(feat, 99, SimpleNamespace(), stats) is None
        assert stats.compute_calls == []

    async def test_under_the_cap_passes_without_raising(self):
        increase = make_increase(10, AbilityScore.STR, 2)
        feat = SimpleNamespace(id=2, ability_score_increases=[increase])
        stats = FakeStatsService()

        assert await validate_ability_score_increase_cap(feat, 10, SimpleNamespace(), stats) is None
        assert len(stats.compute_calls) == 1

    async def test_over_the_cap_raises_with_effective_numbers(self):
        increase = make_increase(10, AbilityScore.DEX, 3)
        feat = SimpleNamespace(id=2, ability_score_increases=[increase])
        stats = FakeStatsService(totals={**TOTALS, "dexterity_total": 19})

        with pytest.raises(AbilityScoreCapExceededException) as exc_info:
            await validate_ability_score_increase_cap(feat, 10, SimpleNamespace(), stats)

        assert exc_info.value.ability == "DEX"
        assert exc_info.value.current_total == 19
        assert exc_info.value.requested == 22

    async def test_raised_cap_allows_beyond_20(self):
        increase = make_increase(10, AbilityScore.STR, 4)
        feat = SimpleNamespace(id=2, ability_score_increases=[increase])
        stats = FakeStatsService(
            totals={**TOTALS, "strength_total": 20},
            caps={**dict.fromkeys(AbilityScore, 20), AbilityScore.STR: 24},
        )

        assert await validate_ability_score_increase_cap(feat, 10, SimpleNamespace(), stats) is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestCheckFeatPrerequisite:
    async def test_no_prerequisite_passes_without_computing(self):
        feat = SimpleNamespace(id=2, prerequisite_ability=None, prerequisite_minimum_score=None)
        stats = FakeStatsService()

        assert await check_feat_prerequisite(SimpleNamespace(), feat, stats) is None
        assert stats.compute_calls == []

    async def test_partial_prerequisite_passes(self):
        feat = SimpleNamespace(id=2, prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=None)
        stats = FakeStatsService()

        assert await check_feat_prerequisite(SimpleNamespace(), feat, stats) is None
        assert stats.compute_calls == []

    async def test_met_prerequisite_passes(self):
        feat = SimpleNamespace(id=2, prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=14)
        stats = FakeStatsService()

        assert await check_feat_prerequisite(SimpleNamespace(), feat, stats) is None

    async def test_unmet_prerequisite_raises(self):
        feat = SimpleNamespace(id=2, prerequisite_ability=AbilityScore.INT, prerequisite_minimum_score=13)
        stats = FakeStatsService(totals={**TOTALS, "intelligence_total": 8})

        with pytest.raises(FeatPrerequisiteNotMetException) as exc_info:
            await check_feat_prerequisite(SimpleNamespace(), feat, stats)

        assert exc_info.value.ability == "INT"
        assert exc_info.value.required_minimum == 13
        assert exc_info.value.actual == 8

    async def test_check_uses_effective_totals_not_base_columns(self):
        feat = SimpleNamespace(id=2, prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=15)
        character = SimpleNamespace(strength=14)
        stats = FakeStatsService(totals={**TOTALS, "strength_total": 16})

        assert await check_feat_prerequisite(character, feat, stats) is None
        assert stats.compute_calls == [character]
