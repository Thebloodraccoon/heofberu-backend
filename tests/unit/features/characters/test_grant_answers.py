"""Unit tests for validating a player's answers against a feature's choice groups."""

from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from app.features.characters.grants.exceptions import (
    ChoiceCountMismatchError,
    ChoiceGroupNotFoundError,
    ChoiceOptionAlreadyPickedError,
    ChoiceOptionNotFoundError,
    SkillResolutionsError,
    SpellResolutionsError,
)
from app.features.characters.grants.schemas import ChoiceAnswerItem, GrantChoicesUpdate
from app.features.characters.grants.service import _validate_answers


def option(option_id, group_id, *, open_skill=False, open_spell=False):
    return SimpleNamespace(
        id=option_id,
        group_id=group_id,
        skill_effects=[SimpleNamespace(skill_id=None)] if open_skill else [],
        spell_effects=[SimpleNamespace(spell_id=None)] if open_spell else [],
    )


def make_feature():
    return SimpleNamespace(
        choice_groups=[
            SimpleNamespace(id=1, pick_count=1, options=[option(10, 1), option(11, 1), option(12, 1, open_skill=True)]),
            SimpleNamespace(id=2, pick_count=2, options=[option(20, 2), option(21, 2), option(22, 2, open_spell=True)]),
        ]
    )


def answer(group_id, option_id):
    return ChoiceAnswerItem(choice_group_id=group_id, choice_option_id=option_id)


@pytest.mark.unit
class TestValidateAnswers:
    def test_returns_the_picked_options_per_group(self):
        picked = _validate_answers(5, make_feature(), [answer(1, 10), answer(2, 20), answer(2, 21)])

        assert {group_id: [o.id for o in options] for group_id, options in picked.items()} == {1: [10], 2: [20, 21]}

    def test_no_answers_validates_to_nothing(self):
        assert _validate_answers(5, make_feature(), []) == {}

    def test_unknown_group_is_rejected(self):
        with pytest.raises(ChoiceGroupNotFoundError):
            _validate_answers(5, make_feature(), [answer(99, 10)])

    def test_unknown_option_is_rejected(self):
        with pytest.raises(ChoiceOptionNotFoundError):
            _validate_answers(5, make_feature(), [answer(1, 404)])

    def test_option_of_another_group_is_rejected(self):
        with pytest.raises(ChoiceOptionNotFoundError):
            _validate_answers(5, make_feature(), [answer(1, 20)])

    def test_same_option_twice_is_rejected(self):
        with pytest.raises(ChoiceOptionAlreadyPickedError):
            _validate_answers(5, make_feature(), [answer(2, 20), answer(2, 20)])

    def test_wrong_pick_count_is_rejected(self):
        with pytest.raises(ChoiceCountMismatchError):
            _validate_answers(5, make_feature(), [answer(2, 20)])

        with pytest.raises(ChoiceCountMismatchError):
            _validate_answers(5, make_feature(), [answer(1, 10), answer(1, 11)])

    def test_open_skill_and_spell_options_are_not_pickable(self):
        with pytest.raises(SkillResolutionsError):
            _validate_answers(5, make_feature(), [answer(1, 12)])

        with pytest.raises(SpellResolutionsError):
            _validate_answers(5, make_feature(), [answer(2, 20), answer(2, 22)])


@pytest.mark.unit
class TestAnswerPayloadBounds:
    def test_oversized_ids_are_a_validation_error_not_a_driver_overflow(self):
        with pytest.raises(ValidationError):
            ChoiceAnswerItem(choice_group_id=2**31, choice_option_id=1)

        with pytest.raises(ValidationError):
            ChoiceAnswerItem(choice_group_id=1, choice_option_id=0)

    def test_answer_list_is_bounded(self):
        with pytest.raises(ValidationError):
            GrantChoicesUpdate(answers=[{"choice_group_id": 1, "choice_option_id": i + 1} for i in range(51)])
