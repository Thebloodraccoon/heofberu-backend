"""Unit tests for the on-read grant effect computation (``characters/grants/effects.py``)."""

from types import SimpleNamespace

import pytest

from app.constants import WeaponProficiency
from app.features.characters.grants.effects import (
    GrantEffects,
    _to_response,
    get_grant_effects_map,
    grant_effects,
    pending_groups,
)
from tests.unit.fakes import FakeAsyncSession


def make_holder(option_id=None, *, skills=(), saves=(), armor=(), weapons=(), spells=()) -> SimpleNamespace:
    return SimpleNamespace(
        id=option_id,
        skill_effects=[
            SimpleNamespace(skill_id=skill_id, grants_expertise=expertise) for skill_id, expertise in skills
        ],
        saving_throw_effects=[SimpleNamespace(ability=ability) for ability in saves],
        armor_effects=[SimpleNamespace(armor_type=armor_type) for armor_type in armor],
        weapon_effects=[SimpleNamespace(weapon_category=category, item_id=item_id) for category, item_id in weapons],
        spell_effects=[SimpleNamespace(spell_id=spell_id) for spell_id in spells],
    )


def make_feature() -> SimpleNamespace:
    feature = make_holder(
        skills=[(1, False)], saves=["STR"], armor=["LIGHT"], weapons=[("MARTIAL", None), (None, 5)], spells=[3]
    )
    plain = make_holder(10, skills=[(7, False)])
    expert = make_holder(11, skills=[(7, True)], spells=[99])
    open_pick = make_holder(12, skills=[(None, False)], spells=[None])
    feature.choice_groups = [SimpleNamespace(id=1, pick_count=1, options=[plain, expert, open_pick])]
    return feature


@pytest.mark.unit
class TestGrantEffects:
    def test_fixed_effects_without_picks(self):
        effects = grant_effects(make_feature(), [])

        assert effects.skills == {1: False}
        assert effects.saving_throws == {"STR"}
        assert effects.armor == {"LIGHT"}
        assert effects.weapons == {("MARTIAL", None), (None, 5)}
        assert effects.spells == {3}

    def test_picked_option_bundle_is_added(self):
        effects = grant_effects(make_feature(), [11])

        assert effects.skills == {1: False, 7: True}
        assert effects.spells == {3, 99}

    def test_reanswer_without_expertise_drops_it(self):
        assert grant_effects(make_feature(), [10]).skills == {1: False, 7: False}

    def test_open_effects_and_unknown_options_contribute_nothing(self):
        effects = grant_effects(make_feature(), [12, 404])

        assert effects.skills == {1: False}
        assert effects.spells == {3}


@pytest.mark.unit
class TestPendingGroups:
    def test_group_without_picks_is_pending(self):
        assert [group.id for group in pending_groups(make_feature(), [])] == [1]

    def test_filled_group_is_not_pending(self):
        assert pending_groups(make_feature(), [SimpleNamespace(choice_group_id=1)]) == []


@pytest.mark.unit
class TestWeaponOrdering:
    def test_weapon_proficiencies_are_sorted_categories_first_then_items(self):
        effects = GrantEffects(
            weapons={(WeaponProficiency.SIMPLE, None), (None, 9), (WeaponProficiency.MARTIAL, None), (None, 2)}
        )

        weapons = _to_response(effects, {}).weapons

        assert [(weapon.weapon_category, weapon.item_id) for weapon in weapons] == [
            (WeaponProficiency.MARTIAL, None),
            (WeaponProficiency.SIMPLE, None),
            (None, 2),
            (None, 9),
        ]


@pytest.mark.unit
@pytest.mark.asyncio
class TestGrantEffectsMapFromLoadedTrees:
    async def test_effects_come_from_the_preloaded_feature_and_picks_with_only_the_spell_lookup(self):
        feature = make_feature()
        grant = SimpleNamespace(id=7, feature=feature, choices=[SimpleNamespace(choice_option_id=11)])

        effects = await get_grant_effects_map(FakeAsyncSession(), [grant])

        assert [(skill.skill_id, skill.is_expertise) for skill in effects[7].skills] == [(1, False), (7, True)]
        assert [saving_throw.ability for saving_throw in effects[7].saving_throws] == ["STR"]
