"""Unit tests for the on-read grant effect computation (``characters/grants/effects.py``)."""

from types import SimpleNamespace

import pytest

from app.constants import SkillEffectMode, WeaponProficiency
from app.features.characters.grants.effects import (
    GrantEffects,
    SkillClaim,
    _to_response,
    get_grant_effects_map,
    grant_effects,
    pending_groups,
)
from tests.helpers import effect_items
from tests.unit.fakes import FakeAsyncSession


def make_holder(option_id=None, *, skills=(), saves=(), armor=(), weapons=(), spells=()) -> SimpleNamespace:
    """``armor`` holds ``(armor_type, item_id)`` pairs, exactly one of the two set per pair."""
    return SimpleNamespace(
        ability_effects=[],
        id=option_id,
        skill_effects=[SimpleNamespace(skill_id=skill_id, mode=mode) for skill_id, mode in skills],
        saving_throw_effects=[SimpleNamespace(ability=ability) for ability in saves],
        armor_effects=[SimpleNamespace(armor_type=armor_type, item_id=item_id) for armor_type, item_id in armor],
        weapon_effects=[SimpleNamespace(weapon_category=category, item_id=item_id) for category, item_id in weapons],
        spell_effects=[SimpleNamespace(spell_id=spell_id) for spell_id in spells],
    )


PROFICIENCY = SkillEffectMode.PROFICIENCY
BOTH = SkillEffectMode.PROFICIENCY_AND_EXPERTISE
EXPERTISE = SkillEffectMode.EXPERTISE
UPGRADE = SkillEffectMode.UPGRADE


def make_feature() -> SimpleNamespace:
    feature = make_holder(
        skills=[(1, PROFICIENCY)],
        saves=["STR"],
        armor=[("LIGHT", None), (None, 40)],
        weapons=[("MARTIAL", None), (None, 5)],
        spells=[3],
    )
    plain = make_holder(10, skills=[(7, PROFICIENCY)])
    expert = make_holder(11, skills=[(7, BOTH)], spells=[99])
    open_pick = make_holder(12, skills=[(None, PROFICIENCY)], spells=[None])
    open_expertise = make_holder(13, skills=[(None, EXPERTISE)])
    feature.choice_groups = [
        SimpleNamespace(id=1, pick_count=1, options=[plain, expert, open_pick]),
        SimpleNamespace(id=2, pick_count=1, options=[open_expertise]),
    ]
    return feature


def flags(effects: GrantEffects) -> dict[int, tuple[bool, bool]]:
    """``skill_id -> (grants, is_expertise)`` of the folded claims."""

    return {skill_id: (claim.grants, claim.is_expertise) for skill_id, claim in effects.skills.items()}


@pytest.mark.unit
class TestGrantEffects:
    def test_fixed_effects_without_picks(self):
        effects = grant_effects(make_feature(), [])

        assert flags(effects) == {1: (True, False)}
        assert effects.saving_throws == {"STR"}
        assert effects.armor == {("LIGHT", None), (None, 40)}
        assert effects.weapons == {("MARTIAL", None), (None, 5)}
        assert effects.spells == {3}

    def test_picked_option_bundle_is_added(self):
        effects = grant_effects(make_feature(), [(11, None, None)])

        assert flags(effects) == {1: (True, False), 7: (True, True)}
        assert effects.spells == {3, 99}

    def test_reanswer_without_expertise_drops_it(self):
        assert flags(grant_effects(make_feature(), [(10, None, None)])) == {1: (True, False), 7: (True, False)}

    def test_open_skill_effect_applies_to_the_named_skill(self):
        effects = grant_effects(make_feature(), [(12, 4, None)])

        assert flags(effects) == {1: (True, False), 4: (True, False)}
        assert effects.spells == {3}

    def test_open_effect_without_a_named_skill_and_unknown_options_contribute_nothing(self):
        effects = grant_effects(make_feature(), [(12, None, None), (404, 2, None)])

        assert flags(effects) == {1: (True, False)}
        assert effects.spells == {3}

    def test_open_spell_effect_gives_the_named_spell(self):
        effects = grant_effects(make_feature(), [(12, 4, 42)])

        assert effects.spells == {3, 42}

    def test_expertise_only_effect_claims_expertise_without_the_proficiency(self):
        effects = grant_effects(make_feature(), [(13, 5, None)])

        assert flags(effects)[5] == (False, True)
        assert effects.skills[5].mode == EXPERTISE

    def test_expertise_on_the_grants_own_proficiency_folds_into_both(self):
        effects = grant_effects(make_feature(), [(12, 4, None), (13, 4, None)])

        assert flags(effects)[4] == (True, True)
        assert effects.skills[4].mode == BOTH


@pytest.mark.unit
class TestSkillClaim:
    def test_upgrade_alone_grants_proficiency_without_expertise(self):
        claim = SkillClaim()
        claim.add(UPGRADE)

        assert (claim.grants, claim.is_expertise, claim.upgrade, claim.mode) == (True, False, True, UPGRADE)

    def test_upgrade_with_the_same_grants_proficiency_is_expertise(self):
        claim = SkillClaim()
        claim.add(UPGRADE)
        claim.add(PROFICIENCY)

        assert (claim.grants, claim.is_expertise, claim.mode) == (True, True, BOTH)


@pytest.mark.unit
class TestPendingGroups:
    def test_group_without_picks_is_pending(self):
        assert [group.id for group in pending_groups(make_feature(), [])] == [1, 2]

    def test_filled_group_is_not_pending(self):
        assert [group.id for group in pending_groups(make_feature(), [SimpleNamespace(choice_group_id=1)])] == [2]


@pytest.mark.unit
class TestArmorOrdering:
    def test_armor_proficiencies_are_sorted_categories_first_then_items(self):
        effects = GrantEffects(armor={(None, 9), ("HEAVY", None), ("LIGHT", None), (None, 2)})

        armor = effect_items(_to_response(effects, {}), "armor")

        assert [(item.armor_type, item.item_id) for item in armor] == [
            ("HEAVY", None),
            ("LIGHT", None),
            (None, 2),
            (None, 9),
        ]


@pytest.mark.unit
class TestWeaponOrdering:
    def test_weapon_proficiencies_are_sorted_categories_first_then_items(self):
        effects = GrantEffects(
            weapons={(WeaponProficiency.SIMPLE, None), (None, 9), (WeaponProficiency.MARTIAL, None), (None, 2)}
        )

        weapons = effect_items(_to_response(effects, {}), "weapon")

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
        grant = SimpleNamespace(
            id=7,
            feature=feature,
            choices=[
                SimpleNamespace(choice_option_id=11, picked_skill_id=None, picked_spell_id=None, picked_ability=None),
                SimpleNamespace(choice_option_id=13, picked_skill_id=1, picked_spell_id=None, picked_ability=None),
            ],
        )

        effects = await get_grant_effects_map(FakeAsyncSession(), [grant])

        assert [(skill.skill_id, skill.is_expertise, skill.mode) for skill in effect_items(effects[7], "skill")] == [
            (1, True, BOTH),
            (7, True, BOTH),
        ]
        assert [saving_throw.ability for saving_throw in effect_items(effects[7], "saving_throw")] == ["STR"]
