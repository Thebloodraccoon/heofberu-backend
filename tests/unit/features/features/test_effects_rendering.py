"""
Unit tests for ``render_effects_summary`` — pure text rendering, no DB.

Covers every effect-type branch, including the two the integration suite
never exercises: an open ("any skill") skill effect and an open
(school/level-filtered) spell effect inside the summary text.
"""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore, ArmorProficiency, SpellLevel, SpellSchool, WeaponProficiency
from app.features.features.effects.rendering import render_effects_summary


def _ability(ability, amount, new_cap=None):
    return SimpleNamespace(ability=ability, amount=amount, new_cap=new_cap)


def _skill(skill_id, grants_expertise=False, skill=None):
    return SimpleNamespace(skill_id=skill_id, grants_expertise=grants_expertise, skill=skill)


def _save(ability):
    return SimpleNamespace(ability=ability)


def _armor(armor_type):
    return SimpleNamespace(armor_type=armor_type)


def _weapon(weapon_category=None, item_id=None, item=None):
    return SimpleNamespace(weapon_category=weapon_category, item_id=item_id, item=item)


def _spell(spell_id=None, spell_school=None, spell_level_max=None, spell=None):
    return SimpleNamespace(spell_id=spell_id, spell_school=spell_school, spell_level_max=spell_level_max, spell=spell)


def _feature(
    ability_effects=(),
    skill_effects=(),
    saving_throw_effects=(),
    armor_effects=(),
    weapon_effects=(),
    spell_effects=(),
    choice_groups=(),
):
    return SimpleNamespace(
        ability_effects=list(ability_effects),
        skill_effects=list(skill_effects),
        saving_throw_effects=list(saving_throw_effects),
        armor_effects=list(armor_effects),
        weapon_effects=list(weapon_effects),
        spell_effects=list(spell_effects),
        choice_groups=list(choice_groups),
    )


def _group(pick_count=1, label="", sort_order=0, options=()):
    return SimpleNamespace(pick_count=pick_count, label=label, sort_order=sort_order, options=list(options))


def _option(
    sort_order=0,
    ability_effects=(),
    skill_effects=(),
    saving_throw_effects=(),
    armor_effects=(),
    weapon_effects=(),
    spell_effects=(),
):
    return SimpleNamespace(
        sort_order=sort_order,
        ability_effects=list(ability_effects),
        skill_effects=list(skill_effects),
        saving_throw_effects=list(saving_throw_effects),
        armor_effects=list(armor_effects),
        weapon_effects=list(weapon_effects),
        spell_effects=list(spell_effects),
    )


@pytest.mark.unit
class TestFixedEffectsSummary:
    def test_no_effects_produces_empty_text(self):
        assert render_effects_summary(_feature()) == ""

    def test_ability_effect_with_new_cap(self):
        text = render_effects_summary(_feature(ability_effects=[_ability(AbilityScore.STR, 4, new_cap=30)]))
        assert "STR" not in text  # rendered in Russian, not the raw enum value
        assert "потолок 30" in text

    def test_closed_skill_effect_uses_catalog_name(self):
        skill = SimpleNamespace(name="Скрытность")
        text = render_effects_summary(_feature(skill_effects=[_skill(7, skill=skill)]))
        assert "«Скрытность»" in text
        assert "экспертизой" not in text

    def test_skill_effect_with_expertise(self):
        skill = SimpleNamespace(name="Скрытность")
        text = render_effects_summary(_feature(skill_effects=[_skill(7, grants_expertise=True, skill=skill)]))
        assert "экспертизой" in text

    def test_open_skill_effect_renders_any_skill_text(self):
        """The branch integration tests never reach: skill_id is None in a FIXED effect."""
        text = render_effects_summary(_feature(skill_effects=[_skill(None)]))
        assert "любым навыком на выбор" in text

    def test_saving_throw_effect(self):
        text = render_effects_summary(_feature(saving_throw_effects=[_save(AbilityScore.WIS)]))
        assert "спасбросок" in text

    def test_armor_effect(self):
        text = render_effects_summary(_feature(armor_effects=[_armor(ArmorProficiency.HEAVY)]))
        assert "тяжёлыми доспехами" in text

    def test_weapon_category_effect(self):
        text = render_effects_summary(_feature(weapon_effects=[_weapon(weapon_category=WeaponProficiency.MARTIAL)]))
        assert "воинским оружием" in text

    def test_weapon_item_effect_uses_catalog_name(self):
        item = SimpleNamespace(name="Длинный меч")
        text = render_effects_summary(_feature(weapon_effects=[_weapon(item_id=3, item=item)]))
        assert "«Длинный меч»" in text

    def test_closed_spell_effect_uses_catalog_name(self):
        spell = SimpleNamespace(name="Огненный шар")
        text = render_effects_summary(_feature(spell_effects=[_spell(spell_id=9, spell=spell)]))
        assert "«Огненный шар»" in text

    def test_open_spell_effect_with_school_and_level_filter(self):
        """The branch integration tests never reach: an open spell filter rendered as text."""
        text = render_effects_summary(
            _feature(
                spell_effects=[
                    _spell(spell_school=SpellSchool.EVOCATION, spell_level_max=SpellLevel.LEVEL_1)
                ]
            )
        )
        assert "любое заклинание" in text
        assert "школы EVOCATION" in text
        assert "не выше LEVEL_1 уровня" in text

    def test_open_spell_effect_with_no_filters(self):
        text = render_effects_summary(_feature(spell_effects=[_spell()]))
        assert text.strip().endswith("любое заклинание.")

    def test_unknown_skill_falls_back_to_id(self):
        """No eager-loaded ``.skill`` relationship — falls back to a numbered placeholder, never crashes."""
        text = render_effects_summary(_feature(skill_effects=[_skill(42, skill=None)]))
        assert "#42" in text


@pytest.mark.unit
class TestChoiceGroupsSummary:
    def test_single_group_single_option(self):
        feature = _feature(
            choice_groups=[
                _group(pick_count=1, label="Choose a skill", options=[_option(skill_effects=[_skill(None)])])
            ]
        )
        text = render_effects_summary(feature)
        assert "Choose a skill (выберите 1 из 1): [1]" in text

    def test_group_without_label_uses_default(self):
        feature = _feature(
            choice_groups=[_group(pick_count=1, label="", options=[_option(ability_effects=[_ability(AbilityScore.STR, 1)])])]
        )
        text = render_effects_summary(feature)
        assert text.startswith("Выбор (выберите 1 из 1):")

    def test_option_with_no_effects_renders_placeholder(self):
        feature = _feature(choice_groups=[_group(pick_count=1, options=[_option()])])
        text = render_effects_summary(feature)
        assert "[1] —" in text

    def test_multiple_groups_and_options_ordered_by_sort_order(self):
        feature = _feature(
            choice_groups=[
                _group(
                    sort_order=1,
                    label="Second",
                    options=[_option(ability_effects=[_ability(AbilityScore.DEX, 1)])],
                ),
                _group(
                    sort_order=0,
                    label="First",
                    options=[
                        _option(sort_order=1, ability_effects=[_ability(AbilityScore.CON, 1)]),
                        _option(sort_order=0, ability_effects=[_ability(AbilityScore.STR, 1)]),
                    ],
                ),
            ]
        )
        text = render_effects_summary(feature)
        lines = text.split("\n")
        assert lines[0].startswith("First")
        assert lines[1].startswith("Second")
        # within "First", sort_order 0 (STR) must render before sort_order 1 (CON)
        first_line_options = lines[0].split(": ", 1)[1]
        assert first_line_options.index("[1]") < first_line_options.index("[2]")

    def test_fixed_effects_and_choice_groups_combined(self):
        feature = _feature(
            ability_effects=[_ability(AbilityScore.STR, 2)],
            choice_groups=[_group(pick_count=1, label="Boon", options=[_option(skill_effects=[_skill(None)])])],
        )
        text = render_effects_summary(feature)
        lines = text.split("\n")
        assert lines[0].startswith("Даёт:")
        assert lines[1].startswith("Boon")
