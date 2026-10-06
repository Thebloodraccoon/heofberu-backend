"""Unit tests for the pure character rules (app/features/characters/crud/rules.py)."""

from types import SimpleNamespace

import pytest

from app.constants import BackgroundSuggestionType
from app.features.characters.crud.exceptions import (
    BackgroundSuggestionIdsRequiredException,
    InvalidBackgroundSuggestionException,
    InvalidHpUpdateException,
    ItemChoiceNotAvailableException,
    TooFewItemChoicesException,
)
from app.features.characters.crud.rules import (
    pick_item_options,
    resolve_background_suggestions,
    resolve_hp_update,
    validate_hp_update,
)
from app.features.characters.crud.schemas import HpUpdate


def make_background(types=("PERSONALITY_TRAIT", "IDEAL", "BOND", "FLAW")):
    return SimpleNamespace(
        id=3,
        suggestions=[
            SimpleNamespace(id=100 + i, suggestion_type=kind, text=f"{kind} text") for i, kind in enumerate(types)
        ],
    )


@pytest.mark.unit
class TestValidateHpUpdate:
    def test_delta_alone_is_valid(self):
        validate_hp_update(HpUpdate(delta=-3))

    def test_absolute_values_alone_are_valid(self):
        validate_hp_update(HpUpdate(current_hp=5))
        validate_hp_update(HpUpdate(temp_hp=5))
        validate_hp_update(HpUpdate(current_hp=5, temp_hp=2))

    def test_delta_with_absolute_is_rejected(self):
        with pytest.raises(InvalidHpUpdateException):
            validate_hp_update(HpUpdate(delta=1, temp_hp=2))

    def test_nothing_given_is_rejected(self):
        with pytest.raises(InvalidHpUpdateException):
            validate_hp_update(HpUpdate())

    def test_zero_delta_counts_as_a_delta(self):
        validate_hp_update(HpUpdate(delta=0))


@pytest.mark.unit
class TestResolveHpUpdate:
    def test_delta_is_clamped_to_zero_and_max(self):
        assert resolve_hp_update(5, 0, 20, HpUpdate(delta=-50)) == (0, 0)
        assert resolve_hp_update(5, 0, 20, HpUpdate(delta=50)) == (20, 0)

    def test_absolute_current_hp_is_clamped(self):
        assert resolve_hp_update(5, 2, 20, HpUpdate(current_hp=99)) == (20, 2)
        assert resolve_hp_update(5, 2, 20, HpUpdate(current_hp=-4)) == (0, 2)

    def test_absolute_temp_hp_only_applies_when_higher(self):
        assert resolve_hp_update(5, 6, 20, HpUpdate(temp_hp=4)) == (5, 6)
        assert resolve_hp_update(5, 6, 20, HpUpdate(temp_hp=9)) == (5, 9)

    def test_absolute_current_and_temp_together(self):
        assert resolve_hp_update(5, 0, 20, HpUpdate(current_hp=8, temp_hp=3)) == (8, 3)


@pytest.mark.unit
class TestResolveBackgroundSuggestions:
    def test_one_suggestion_per_type_fills_the_personality_card(self):
        result = resolve_background_suggestions(make_background(), [100, 101, 102, 103])

        assert result == {
            "personality_traits": "PERSONALITY_TRAIT text",
            "ideals": "IDEAL text",
            "bonds": "BOND text",
            "flaws": "FLAW text",
        }

    def test_wrong_number_of_ids_is_rejected(self):
        with pytest.raises(BackgroundSuggestionIdsRequiredException) as exc_info:
            resolve_background_suggestions(make_background(), [100, 101])

        assert exc_info.value.requested == 2

    def test_foreign_suggestion_is_rejected(self):
        with pytest.raises(InvalidBackgroundSuggestionException) as exc_info:
            resolve_background_suggestions(make_background(), [100, 101, 102, 999])

        assert exc_info.value.suggestion_id == 999

    def test_two_suggestions_of_the_same_type_are_rejected(self):
        background = make_background(("PERSONALITY_TRAIT", "PERSONALITY_TRAIT", "BOND", "FLAW"))

        with pytest.raises(BackgroundSuggestionIdsRequiredException):
            resolve_background_suggestions(background, [100, 101, 102, 103])

    def test_every_type_must_be_covered(self):
        assert len(BackgroundSuggestionType) == 4


def make_option(option_id, group_id=1, item_id=20, quantity=1):
    return SimpleNamespace(id=option_id, group_id=group_id, item_id=item_id, quantity=quantity)


@pytest.mark.unit
class TestPickItemOptions:
    def test_no_groups_and_no_choices_is_empty(self):
        assert pick_item_options([], []) == []

    def test_returns_the_chosen_options_in_order(self):
        a, b = make_option(1), make_option(2)
        group = SimpleNamespace(id=1, pick_count=1, options=[a, b])

        assert pick_item_options([group], [2]) == [b]

    def test_unknown_option_is_rejected(self):
        group = SimpleNamespace(id=1, pick_count=1, options=[make_option(1)])

        with pytest.raises(ItemChoiceNotAvailableException):
            pick_item_options([group], [7])

    def test_too_many_picks_are_rejected(self):
        group = SimpleNamespace(id=1, pick_count=1, options=[make_option(1), make_option(2)])

        with pytest.raises(TooFewItemChoicesException) as exc_info:
            pick_item_options([group], [1, 2])

        assert exc_info.value.chosen == 2
