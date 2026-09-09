"""Shared helpers for gm_panel unit tests."""

from types import SimpleNamespace

from tests.unit.features.characters.conftest import make_feat_with_choice_groups as make_feat


def make_ability_effect(effect_id, ability, amount):
    """Build a single ability-effect SimpleNamespace (mirrors FeatureAbilityScoreEffect)."""
    return SimpleNamespace(id=effect_id, ability=ability, amount=amount)
