"""Unit tests for validating a player's answers against a feature's choice groups."""

from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from app.constants import AbilityScore, ChoiceType
from app.features.characters.grants.exceptions import (
    AbilityPickCapExceededError,
    ChoiceCountMismatchError,
    ChoiceGroupNotFoundError,
    ChoiceOptionAlreadyPickedError,
    ChoiceOptionNotFoundError,
    SkillPickRequiredError,
    SpellPickRequiredError,
    UnexpectedSkillPickError,
    UnexpectedSpellPickError,
)
from app.features.characters.grants.schemas import ChoiceAnswerItem, GrantChoicesUpdate
from app.features.characters.grants.service import _ensure_picks_within_cap, _validate_answers


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
            SimpleNamespace(id=3, pick_count=2, options=[option(30, 3, open_skill=True)]),
        ]
    )


def answer(group_id, option_id, skill_id=None, spell_id=None):
    return ChoiceAnswerItem(
        choice_group_id=group_id, choice_option_id=option_id, skill_id=skill_id, spell_id=spell_id
    )


def picked_ids(picked):
    return {group_id: [(pick.option.id, pick.skill_id) for pick in picks] for group_id, picks in picked.items()}


def picked_spells(picked):
    return {group_id: [(pick.option.id, pick.spell_id) for pick in picks] for group_id, picks in picked.items()}


@pytest.mark.unit
class TestValidateAnswers:
    def test_returns_the_picked_options_per_group(self):
        picked = _validate_answers(5, make_feature(), [answer(1, 10), answer(2, 20), answer(2, 21)])

        assert picked_ids(picked) == {1: [(10, None)], 2: [(20, None), (21, None)]}

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

    def test_open_skill_option_is_picked_with_a_named_skill(self):
        picked = _validate_answers(5, make_feature(), [answer(1, 12, skill_id=4)])

        assert picked_ids(picked) == {1: [(12, 4)]}

    def test_one_open_option_fills_a_group_with_different_skills(self):
        picked = _validate_answers(5, make_feature(), [answer(3, 30, skill_id=4), answer(3, 30, skill_id=5)])

        assert picked_ids(picked) == {3: [(30, 4), (30, 5)]}

    def test_open_option_with_the_same_skill_twice_is_rejected(self):
        with pytest.raises(ChoiceOptionAlreadyPickedError):
            _validate_answers(5, make_feature(), [answer(3, 30, skill_id=4), answer(3, 30, skill_id=4)])

    def test_open_skill_option_without_a_skill_is_rejected(self):
        with pytest.raises(SkillPickRequiredError):
            _validate_answers(5, make_feature(), [answer(1, 12)])

    def test_skill_on_a_concrete_option_is_rejected(self):
        with pytest.raises(UnexpectedSkillPickError):
            _validate_answers(5, make_feature(), [answer(1, 10, skill_id=4)])

    def test_open_spell_option_is_picked_with_a_named_spell(self):
        picked = _validate_answers(5, make_feature(), [answer(2, 20), answer(2, 22, spell_id=7)])

        assert picked_spells(picked) == {2: [(20, None), (22, 7)]}

    def test_one_open_spell_option_fills_a_group_with_different_spells(self):
        picked = _validate_answers(5, make_feature(), [answer(2, 22, spell_id=7), answer(2, 22, spell_id=8)])

        assert picked_spells(picked) == {2: [(22, 7), (22, 8)]}

    def test_open_spell_option_with_the_same_spell_twice_is_rejected(self):
        with pytest.raises(ChoiceOptionAlreadyPickedError):
            _validate_answers(5, make_feature(), [answer(2, 22, spell_id=7), answer(2, 22, spell_id=7)])

    def test_open_spell_option_without_a_spell_is_rejected(self):
        with pytest.raises(SpellPickRequiredError):
            _validate_answers(5, make_feature(), [answer(2, 20), answer(2, 22)])

    def test_spell_on_a_concrete_option_is_rejected(self):
        with pytest.raises(UnexpectedSpellPickError):
            _validate_answers(5, make_feature(), [answer(2, 20, spell_id=7), answer(2, 21)])


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


def ability_feature(*, amount=1, new_cap=None):
    """One ABILITY_SCORE group (id 5) whose option 50 raises STR by ``amount``, plus a non-ability group (id 6)."""
    ability_option = SimpleNamespace(
        id=50,
        group_id=5,
        ability_effects=[SimpleNamespace(ability=AbilityScore.STR, amount=amount, new_cap=new_cap)],
    )
    other_option = SimpleNamespace(id=60, group_id=6, ability_effects=[])
    return SimpleNamespace(
        choice_groups=[
            SimpleNamespace(id=5, choice_type=ChoiceType.ABILITY_SCORE, pick_count=1, options=[ability_option]),
            SimpleNamespace(id=6, choice_type=ChoiceType.SKILL, pick_count=1, options=[other_option]),
        ]
    )


@pytest.mark.unit
class TestEnsurePicksWithinCap:
    def test_pick_reaching_exactly_twenty_is_allowed(self):
        _ensure_picks_within_cap(ability_feature(), [answer(5, 50)], {"strength_total": 20})

    def test_pick_above_twenty_is_rejected_with_the_pre_pick_total(self):
        with pytest.raises(AbilityPickCapExceededError) as exc_info:
            _ensure_picks_within_cap(ability_feature(), [answer(5, 50)], {"strength_total": 21})

        assert (exc_info.value.current_total, exc_info.value.requested, exc_info.value.cap) == (20, 21, 20)
        assert exc_info.value.status_code == 400

    def test_a_feature_new_cap_lifts_the_limit(self):
        _ensure_picks_within_cap(ability_feature(new_cap=30), [answer(5, 50)], {"strength_total": 25})

    def test_unpicked_options_are_not_checked(self):
        _ensure_picks_within_cap(ability_feature(), [answer(6, 60)], {"strength_total": 25})

    def test_negative_amounts_are_never_rejected(self):
        _ensure_picks_within_cap(ability_feature(amount=-1), [answer(5, 50)], {"strength_total": 25})
