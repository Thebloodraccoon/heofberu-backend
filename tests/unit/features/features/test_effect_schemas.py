"""Unit tests for the effect-engine write schemas: bounds, duplicates, fixed-target rules, unknown keys."""

from pydantic import ValidationError
import pytest

from app.features.features.effects.schemas import (
    AbilityEffectItem,
    ChoiceGroupPatch,
    ChoiceGroupPayload,
    ChoiceOptionPatch,
    ChoiceOptionPayload,
    FeatureEffectsUpdate,
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

    def test_open_skill_in_a_skill_group_still_rejected(self):
        with pytest.raises(ValidationError, match="skill_id is required"):
            ChoiceGroupPayload(choice_type="SKILL", options=[{"effects": [{"effect_type": "skill", "items": [{}]}]}])


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

    def test_fixed_spell_requires_spell_id(self):
        with pytest.raises(ValidationError, match="spell_effects entry requires spell_id"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": "spell", "items": [{}]}])

    @pytest.mark.parametrize(
        ("field", "items"),
        [
            ("ability_effects", [{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 2}]),
            ("skill_effects", [{"skill_id": 1}, {"skill_id": 1, "grants_expertise": True}]),
            ("saving_throw_effects", [{"ability": "WIS"}, {"ability": "WIS"}]),
            ("armor_effects", [{"armor_type": "LIGHT"}, {"armor_type": "LIGHT"}]),
            ("weapon_effects", [{"item_id": 2}, {"item_id": 2}]),
            ("weapon_effects", [{"weapon_category": "MARTIAL"}, {"weapon_category": "MARTIAL"}]),
            ("spell_effects", [{"spell_id": 7}, {"spell_id": 7}]),
        ],
    )
    def test_duplicate_effects_rejected(self, field, items):
        with pytest.raises(ValidationError, match=f"Duplicate entry in {field}"):
            FeatureEffectsUpdate(static_groups=[{"effect_type": field.removesuffix("_effects"), "items": items}])

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
