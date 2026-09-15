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


def _group(pick_count=1, sort_order=0, options=()):
    return SimpleNamespace(pick_count=pick_count, sort_order=sort_order, options=list(options))


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
class TestStaticEffectsSummary:
    def test_no_effects_produces_empty_text(self):
        assert render_effects_summary(_feature()) == ""

    def test_single_type_wraps_in_p_and_ul(self):
        text = render_effects_summary(_feature(ability_effects=[_ability(AbilityScore.STR, 4, new_cap=30)]))
        assert text.startswith("<p>Вы получаете:</p><ul>")
        assert text.endswith("</ul>")
        assert "Сила +4 (потолок 30)" in text

    def test_ability_effect_uses_nominative_form(self):
        text = render_effects_summary(_feature(ability_effects=[_ability(AbilityScore.STR, 1)]))
        assert "Сила +1" in text
        assert "Силу" not in text

    def test_closed_skill_effect_uses_catalog_name(self):
        skill = SimpleNamespace(name="Скрытность")
        text = render_effects_summary(_feature(skill_effects=[_skill(7, skill=skill)]))
        assert "Владения навыками: «Скрытность»" in text
        assert "экспертизой" not in text

    def test_skill_effect_with_expertise(self):
        skill = SimpleNamespace(name="Скрытность")
        text = render_effects_summary(_feature(skill_effects=[_skill(7, grants_expertise=True, skill=skill)]))
        assert "экспертизой" in text

    def test_open_skill_effect_renders_any_skill_text(self):
        """The branch integration tests never reach: skill_id is None in a FIXED effect."""
        text = render_effects_summary(_feature(skill_effects=[_skill(None)]))
        assert "любым навыком на выбор" in text

    def test_saving_throw_effect_uses_nominative_form(self):
        text = render_effects_summary(_feature(saving_throw_effects=[_save(AbilityScore.WIS)]))
        assert "Спасброски: Мудрость" in text

    def test_armor_effect_uses_nominative_form(self):
        text = render_effects_summary(_feature(armor_effects=[_armor(ArmorProficiency.HEAVY)]))
        assert "Владения доспехами: тяжёлые доспехи" in text

    def test_weapon_category_effect_uses_nominative_form(self):
        text = render_effects_summary(_feature(weapon_effects=[_weapon(weapon_category=WeaponProficiency.MARTIAL)]))
        assert "Владения оружием: воинское оружие" in text

    def test_weapon_item_effect_uses_catalog_name(self):
        item = SimpleNamespace(name="Длинный меч")
        text = render_effects_summary(_feature(weapon_effects=[_weapon(item_id=3, item=item)]))
        assert "«Длинный меч»" in text

    def test_closed_spell_effect_links_to_spell_id(self):
        spell = SimpleNamespace(name="Огненный шар")
        text = render_effects_summary(_feature(spell_effects=[_spell(spell_id=9, spell=spell)]))
        assert '<a href="/api/spells/9">Огненный шар</a>' in text
        assert "«Огненный шар»" not in text

    def test_open_spell_effect_with_school_and_level_filter(self):
        """The branch integration tests never reach: an open spell filter rendered as text."""
        text = render_effects_summary(
            _feature(
                spell_effects=[
                    _spell(spell_school=SpellSchool.EVOCATION, spell_level_max=SpellLevel.LEVEL_1)
                ]
            )
        )
        assert "школы EVOCATION" in text
        assert "не выше LEVEL_1 уровня" in text

    def test_open_spell_effect_with_no_filters(self):
        text = render_effects_summary(_feature(spell_effects=[_spell()]))
        assert "Заклинания: любое" in text

    def test_unknown_skill_falls_back_to_id(self):
        """No eager-loaded ``.skill`` relationship — falls back to a numbered placeholder, never crashes."""
        text = render_effects_summary(_feature(skill_effects=[_skill(42, skill=None)]))
        assert "#42" in text

    def test_group_order_is_fixed(self):
        text = render_effects_summary(
            _feature(
                spell_effects=[_spell()],
                ability_effects=[_ability(AbilityScore.STR, 1)],
                armor_effects=[_armor(ArmorProficiency.LIGHT)],
            )
        )
        assert text.index("Изменение характеристик") < text.index("Владения доспехами") < text.index("Заклинания")


@pytest.mark.unit
class TestChoiceGroupsSummary:
    def test_single_group_single_option_no_pick_prefix(self):
        feature = _feature(choice_groups=[_group(pick_count=1, options=[_option(skill_effects=[_skill(None)])])])
        text = render_effects_summary(feature)
        assert text.startswith("<p>У вас есть выбор:</p><ul>")
        assert "Выберите" not in text
        assert "владение любым навыком на выбор" in text

    def test_multiple_options_joined_by_or(self):
        feature = _feature(
            choice_groups=[
                _group(
                    pick_count=1,
                    options=[
                        _option(ability_effects=[_ability(AbilityScore.STR, 1)]),
                        _option(ability_effects=[_ability(AbilityScore.DEX, 1)]),
                    ],
                )
            ]
        )
        text = render_effects_summary(feature)
        assert "Сила +1 или Ловкость +1" in text

    def test_pick_count_above_one_gets_prefix(self):
        feature = _feature(
            choice_groups=[
                _group(
                    pick_count=2,
                    options=[
                        _option(skill_effects=[_skill(1, skill=SimpleNamespace(name="Атлетика"))]),
                        _option(skill_effects=[_skill(2, skill=SimpleNamespace(name="Скрытность"))]),
                    ],
                )
            ]
        )
        text = render_effects_summary(feature)
        assert "Выберите 2: владение навыком «Атлетика» или владение навыком «Скрытность»" in text

    def test_option_with_no_effects_renders_placeholder(self):
        feature = _feature(choice_groups=[_group(pick_count=1, options=[_option()])])
        text = render_effects_summary(feature)
        assert "<li>—</li>" in text

    def test_groups_ordered_by_sort_order(self):
        feature = _feature(
            choice_groups=[
                _group(sort_order=1, options=[_option(ability_effects=[_ability(AbilityScore.DEX, 1)])]),
                _group(sort_order=0, options=[_option(ability_effects=[_ability(AbilityScore.STR, 1)])]),
            ]
        )
        text = render_effects_summary(feature)
        assert text.index("Сила +1") < text.index("Ловкость +1")

    def test_option_with_multiple_effects_joined_by_comma(self):
        feature = _feature(
            choice_groups=[
                _group(
                    pick_count=1,
                    options=[
                        _option(
                            skill_effects=[_skill(1, skill=SimpleNamespace(name="Атлетика"))],
                            saving_throw_effects=[_save(AbilityScore.DEX)],
                        )
                    ],
                )
            ]
        )
        text = render_effects_summary(feature)
        assert "владение навыком «Атлетика», спасбросок Ловкость" in text

    def test_static_and_choices_separated_by_blank_line(self):
        feature = _feature(
            ability_effects=[_ability(AbilityScore.STR, 2)],
            choice_groups=[_group(pick_count=1, options=[_option(skill_effects=[_skill(None)])])],
        )
        text = render_effects_summary(feature)
        static_html, blank, choice_html = text.split("\n")
        assert static_html.startswith("<p>Вы получаете:</p>")
        assert blank == ""
        assert choice_html.startswith("<p>У вас есть выбор:</p>")

    def test_no_choice_groups_omits_the_block_entirely(self):
        text = render_effects_summary(_feature(ability_effects=[_ability(AbilityScore.STR, 1)]))
        assert "У вас есть выбор" not in text
