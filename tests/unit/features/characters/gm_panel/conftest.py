"""Shared helpers for gm_panel unit tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def make_ability_effect(effect_id, ability, amount):
    """Build a single ability-effect SimpleNamespace (mirrors FeatureAbilityScoreEffect)."""
    return SimpleNamespace(id=effect_id, ability=ability, amount=amount)


@pytest.fixture(autouse=True)
def stub_row_lock(monkeypatch):
    """The row lock is a ``SELECT ... FOR UPDATE`` on a real DB; the fake sessions here have nothing to lock."""

    lock = AsyncMock()
    for module in ("feats", "features", "items", "proficiencies"):
        monkeypatch.setattr(f"app.features.characters.gm_panel.{module}.service.lock_character", lock)
    return lock
