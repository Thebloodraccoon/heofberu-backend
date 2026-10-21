"""Unit tests for the effect-engine write schemas: bounds, duplicates, fixed-target rules, unknown keys."""

from pydantic import ValidationError
import pytest

from app.features.features.effects.schemas import (
    AbilityEffectItem,
    ArmorEffectItem,
    ChoiceGroupPatch,
    ChoiceGroupPayload,
    ChoiceOptionPatch,
    ChoiceOptionPayload,
    FeatureEffectsUpdate,
    OptionEffectsUpdate,
    SpellEffectItem,
)


@pytest.mark.unit
class TestChoiceGroupBounds:
    @pytest.mark.parametrize("pick_count", [0, -1, 51])
    def test_pick_count_outside_range_rejected(self, pick_count):
        with pytest.raises(ValidationError, match="pick_count"):
            ChoiceGroupPayload(pick_count=pick_count, choice_type="SKILL")

    def test_pick_count_one_is_allowed(self):
        assert ChoiceGroupPayload(pick_count=1, choice_type="SKILL").pick_count == 1

    def test_too_many_options_rejected(self):
        with pytest.raises(ValidationError, match="options"):
            ChoiceGroupPayload(choice_type="SKILL", options=[{}] * 51)

    def test_negative_sort_order_rejected(self):
        with pytest.raises(ValidationError, match="sort_order"):
            ChoiceOptionPayload(sort_order=-1)

    def test_unknown_key_in_group_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            ChoiceGroupPayload(choice_type="SKILL", feature_id=1)

    def test_duplicate_option_ids_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate option id"):
            ChoiceGroupPayload(choice_type="SKILL", options=[{"id": 3}, {"id": 3}])


@pytest.mark.unit
class TestOptionEffectDuplicates:
    def test_duplicate_skill_in_one_option_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate entry in skill_effects"):
            ChoiceOptionPayload(effects=[{"effect_type": "skill", "items": [{"skill_id": 1}, {"skill_id": 1}]}])

    def test_duplicate_effect_row_ids_in_option_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate id in ability_effects"):
            ChoiceOptionPayload(
                effects=[
                    {
                        "effect_type": "ability",
                        "items": [
                            {"id": 4, "ability": "STR", "amount": 1},
                            {"id": 4, "ability": "DEX", "amount": 1},
                        ],
                    }
                ]
            )

    def test_distinct_effects_in_one_option_are_fine(self):
        option = ChoiceOptionPayload(effects=[{"effect_type": "skill", "items": [{"skill_id": 1}, {"skill_id": 2}]}])
        assert len(option.skill_effects) == 2

    def test_open_skill_in_a_skill_group_is_accepted(self):
        group = ChoiceGroupPayload(
            choice_type="SKILL", options=[{"effects": [{"effect_type": "skill", "items": [{"mode": "EXPERTISE"}]}]}]
        )

        (effect,) = group.options[0].skill_effects
        assert effect.skill_id is None
        assert effect.mode == "EXPERTISE"

    def test_two_open_skill_effects_in_one_option_are_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate entry in skill_effects"):
            ChoiceOptionPayload(effects=[{"effect_type": "skill", "items": [{}, {"mode": "EXPERTISE"}]}])

    def test_open_spell_in_a_spell_group_is_accepted_with_its_filter(self):
        group = ChoiceGroupPayload(
            choice_type="SPELL",
            options=[
                {
                    "effects": [
                        {
                            "effect_type": "spell",
                            "items": [{"castable_only": True, "schools": ["EVOCATION", "EVOCATION"]}],
                        }
                    ]
                }
            ],
        )

        (effect,) = group.options[0].spell_effects
        assert effect.spell_id is None
        assert effect.castable_only is True
        assert effect.schools == ["EVOCATION"]

    def test_two_open_spell_effects_in_one_option_are_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate entry in spell_effects"):
            ChoiceOptionPayload(effects=[{"effect_type": "spell", "items": [{}, {"ritual_only": True}]}])

    def test_unknown_skill_mode_is_rejected(self):
        with pytest.raises(ValidationError):
            ChoiceOptionPayload(effects=[{"effect_type": "skill", "items": [{"skill_id": 1, "mode": "DOUBLE"}]}])


@pytest.mark.unit
class TestFixedEffectsUpdate:
    def test_omitted_types_are_none_not_empty(self):
        data = FeatureEffectsUpdate(static_groups=[{"effect_type": "weapon", "items": [{"item_id": 3}]}])
        assert data.ability_effects is None
        assert data.skill_effects is None
        assert data.weapon_effects is not None

    def test_empty_items_list_is_kept(self):
        assert FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": []}]).armor_effects == []

    def test_fixed_skill_requires_skill_id(self):
        with pytest.raises(ValidationError, match="skill_effects entry requires skill_id"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": "skill", "items": [{}]}])

    def test_option_effects_accept_an_open_skill(self):
        data = OptionEffectsUpdate(static_groups=[{"effect_type": "skill", "items": [{"mode": "UPGRADE"}]}])

        assert data.skill_effects[0].skill_id is None

    def test_option_effects_accept_an_open_spell(self):
        data = OptionEffectsUpdate(static_groups=[{"effect_type": "spell", "items": [{"max_level": "LEVEL_5"}]}])

        assert data.spell_effects[0].spell_id is None
        assert data.spell_effects[0].max_level == "LEVEL_5"

    def test_fixed_spell_requires_spell_id(self):
        with pytest.raises(ValidationError, match="spell_effects entry requires spell_id"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": "spell", "items": [{}]}])

    @pytest.mark.parametrize(
        ("field", "items"),
        [
            ("ability_effects", [{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 2}]),
            ("skill_effects", [{"skill_id": 1}, {"skill_id": 1, "mode": "PROFICIENCY_AND_EXPERTISE"}]),
            ("saving_throw_effects", [{"ability": "WIS"}, {"ability": "WIS"}]),
            ("armor_effects", [{"armor_type": "LIGHT"}, {"armor_type": "LIGHT"}]),
            ("armor_effects", [{"item_id": 40}, {"item_id": 40}]),
            ("weapon_effects", [{"item_id": 2}, {"item_id": 2}]),
            ("weapon_effects", [{"weapon_category": "MARTIAL"}, {"weapon_category": "MARTIAL"}]),
            ("spell_effects", [{"spell_id": 7}, {"spell_id": 7}]),
        ],
    )
    def test_duplicate_effects_rejected(self, field, items):
        with pytest.raises(ValidationError, match=f"Duplicate entry in {field}"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": field.removesuffix("_effects"), "items": items}])

    def test_category_and_item_armor_effects_do_not_collide(self):
        data = FeatureEffectsUpdate(
            static_groups=[{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}, {"item_id": 40}]}]
        )

        assert [(effect.armor_type, effect.item_id) for effect in data.armor_effects] == [("LIGHT", None), (None, 40)]

    def test_duplicate_row_ids_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate id in armor_effects"):
            FeatureEffectsUpdate(
                static_groups=[
                    {
                        "effect_type": "armor",
                        "items": [{"id": 1, "armor_type": "LIGHT"}, {"id": 1, "armor_type": "HEAVY"}],
                    }
                ]
            )

    def test_unknown_top_level_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            FeatureEffectsUpdate(weapon_effect=[{"item_id": 3}])

    def test_list_length_is_bounded(self):
        with pytest.raises(ValidationError, match="items"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}] * 51}])


@pytest.mark.unit
class TestChoiceGroupPatch:
    def test_only_sent_fields_are_set(self):
        patch = ChoiceGroupPatch(pick_count=2)
        assert patch.model_dump(exclude_unset=True) == {"pick_count": 2}

    def test_empty_patch_is_allowed(self):
        assert ChoiceGroupPatch().model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize("field", ["pick_count", "sort_order"])
    def test_explicit_null_rejected(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            ChoiceGroupPatch(**{field: None})

    @pytest.mark.parametrize("pick_count", [0, 51])
    def test_pick_count_outside_range_rejected(self, pick_count):
        with pytest.raises(ValidationError, match="pick_count"):
            ChoiceGroupPatch(pick_count=pick_count)

    def test_negative_sort_order_rejected(self):
        with pytest.raises(ValidationError, match="sort_order"):
            ChoiceGroupPatch(sort_order=-1)

    def test_choice_type_cannot_be_patched(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            ChoiceGroupPatch(choice_type="SPELL")


@pytest.mark.unit
class TestChoiceOptionPatch:
    def test_sort_order_is_accepted(self):
        assert ChoiceOptionPatch(sort_order=3).sort_order == 3

    def test_sort_order_is_required(self):
        with pytest.raises(ValidationError, match="sort_order"):
            ChoiceOptionPatch()

    def test_negative_sort_order_rejected(self):
        with pytest.raises(ValidationError, match="sort_order"):
            ChoiceOptionPatch(sort_order=-1)

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            ChoiceOptionPatch(sort_order=1, effects=[])


@pytest.mark.unit
class TestArmorEffectItem:
    def test_item_alone_is_accepted(self):
        item = ArmorEffectItem(item_id=40)

        assert item.armor_type is None
        assert item.item_id == 40

    def test_category_alone_is_accepted(self):
        item = ArmorEffectItem(armor_type="HEAVY")

        assert item.armor_type == "HEAVY"
        assert item.item_id is None

    def test_both_set_rejected(self):
        with pytest.raises(ValidationError, match="Set exactly one of armor_type or item_id"):
            ArmorEffectItem(armor_type="LIGHT", item_id=40)

    def test_neither_set_rejected(self):
        with pytest.raises(ValidationError, match="Set exactly one of armor_type or item_id"):
            ArmorEffectItem()

    def test_non_positive_item_id_rejected(self):
        with pytest.raises(ValidationError, match="item_id"):
            ArmorEffectItem(item_id=0)


@pytest.mark.unit
class TestEffectItemBounds:
    def test_amount_beyond_thirty_rejected(self):
        with pytest.raises(ValidationError, match="amount"):
            AbilityEffectItem(ability="STR", amount=31)

    def test_amount_below_minus_thirty_rejected(self):
        with pytest.raises(ValidationError, match="amount"):
            AbilityEffectItem(ability="STR", amount=-31)

    def test_negative_amount_within_range_allowed(self):
        assert AbilityEffectItem(ability="STR", amount=-3).amount == -3

    def test_oversized_catalog_id_rejected_instead_of_overflowing_the_driver(self):
        with pytest.raises(ValidationError, match="skill_id"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": "skill", "items": [{"skill_id": 2**31}]}])

    def test_non_positive_row_id_rejected(self):
        with pytest.raises(ValidationError, match="id"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"id": 0, "armor_type": "LIGHT"}]}])

    def test_unknown_key_in_item_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            AbilityEffectItem(ability="STR", amount=1, bogus=True)


@pytest.mark.unit
class TestSpellEffectFilter:
    def test_defaults_do_not_restrict(self):
        assert SpellEffectItem().has_filter is False

    @pytest.mark.parametrize(
        "spell_filter",
        [
            {"class_ids": [1]},
            {"min_level": "CANTRIP"},
            {"max_level": "LEVEL_3"},
            {"castable_only": True},
            {"schools": ["ABJURATION"]},
            {"ritual_only": True},
        ],
    )
    def test_a_concrete_spell_carries_no_filter(self, spell_filter):
        assert SpellEffectItem(**spell_filter).has_filter is True
        with pytest.raises(ValidationError, match="only to an open"):
            SpellEffectItem(spell_id=1, **spell_filter)

    def test_inverted_level_range_is_rejected(self):
        with pytest.raises(ValidationError, match="min_level must not be above max_level"):
            SpellEffectItem(min_level="LEVEL_6", max_level="LEVEL_5")

    def test_exact_level_range_is_fine(self):
        item = SpellEffectItem(min_level="LEVEL_6", max_level="LEVEL_6")

        assert (item.min_level, item.max_level) == ("LEVEL_6", "LEVEL_6")

    def test_repeated_classes_are_dropped(self):
        assert SpellEffectItem(class_ids=[3, 1, 3]).class_ids == [3, 1]


@pytest.mark.unit
class TestSpellEffectSummary:
    def test_an_open_effect_reads_as_its_filter_phrases(self):
        item = SpellEffectItem(max_level="LEVEL_3", schools=["ABJURATION"])

        assert item.summary == ["до 3-го уровня", "школа: Ограждение"]

    def test_class_names_replace_the_count_when_known(self):
        item = SpellEffectItem(class_ids=[1, 2], class_names=["Бард", "Жрец"])

        assert item.summary == ["из списка: Бард, Жрец"]

    def test_without_class_names_the_count_is_described(self):
        assert SpellEffectItem(class_ids=[1]).summary == ["из списка класса"]
        assert SpellEffectItem(class_ids=[1, 2]).summary == ["из списков выбранных классов"]

    def test_an_open_effect_without_filters_has_no_phrases(self):
        assert SpellEffectItem().summary == []

    def test_a_concrete_spell_has_no_summary(self):
        assert SpellEffectItem(spell_id=5).summary == []

    def test_class_names_and_summary_are_not_row_fields(self):
        item = SpellEffectItem(class_ids=[1], class_names=["Бард"])

        dumped = item.model_dump(exclude={"id", "summary"})

        assert "class_names" not in dumped
        assert "summary" not in dumped
        assert dumped["class_ids"] == [1]
