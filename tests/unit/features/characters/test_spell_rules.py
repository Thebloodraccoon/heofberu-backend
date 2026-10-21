"""Unit tests for the open ("any spell") pick rules (``characters/grants/spell_rules.py``)."""

from types import SimpleNamespace

import pytest

from app.constants import SpellLevel, SpellSchool
from app.features.characters.grants.effects import GrantEffects
from app.features.characters.grants.spell_rules import (
    SpellFacts,
    SpellOwnership,
    SpellSources,
    allowed_spells,
    build_spell_sources,
    open_spell_effect,
    spell_refusal,
)


def open_effect(**spell_filter) -> SimpleNamespace:
    return SimpleNamespace(
        spell_id=None,
        class_ids=spell_filter.get("class_ids", []),
        min_level=spell_filter.get("min_level"),
        max_level=spell_filter.get("max_level"),
        castable_only=spell_filter.get("castable_only", False),
        schools=spell_filter.get("schools", []),
        ritual_only=spell_filter.get("ritual_only", False),
    )


def spell(spell_id, level=SpellLevel.LEVEL_1, school=SpellSchool.EVOCATION, *, ritual=False, classes=()) -> SpellFacts:
    return SpellFacts(
        id=spell_id,
        name=f"spell {spell_id}",
        level=level,
        school=school,
        is_ritual=ritual,
        class_ids=frozenset(classes),
    )


def ownership(castable=(SpellLevel.CANTRIP, SpellLevel.LEVEL_1, SpellLevel.LEVEL_2), owned=()) -> SpellOwnership:
    return SpellOwnership(castable_levels=set(castable), owned=set(owned))


@pytest.mark.unit
class TestSpellRefusal:
    def test_an_unfiltered_effect_takes_any_new_spell(self):
        assert spell_refusal(open_effect(), spell(1, SpellLevel.LEVEL_9), ownership()) is None

    def test_class_lists(self):
        effect = open_effect(class_ids=[1, 2])

        assert spell_refusal(effect, spell(1, classes=[2, 5]), ownership()) is None
        refusal = spell_refusal(effect, spell(2, classes=[5]), ownership())
        assert refusal == "it isn't on the class lists the option allows"
        # a spell tied to no class is on every list
        assert spell_refusal(effect, spell(3), ownership()) is None

    def test_level_range(self):
        effect = open_effect(min_level=SpellLevel.LEVEL_1, max_level=SpellLevel.LEVEL_3)

        below = spell_refusal(effect, spell(1, SpellLevel.CANTRIP), ownership())
        above = spell_refusal(effect, spell(3, SpellLevel.LEVEL_4), ownership())

        assert below == "its level is below the option's range"
        assert spell_refusal(effect, spell(2, SpellLevel.LEVEL_3), ownership()) is None
        assert above == "its level is above the option's range"

    def test_castable_allows_cantrips_and_slot_levels_only(self):
        effect = open_effect(castable_only=True)
        no_cantrip_slots = ownership(castable=[SpellLevel.LEVEL_1])

        assert spell_refusal(effect, spell(1, SpellLevel.CANTRIP), no_cantrip_slots) is None
        assert spell_refusal(effect, spell(2, SpellLevel.LEVEL_1), no_cantrip_slots) is None
        assert (
            spell_refusal(effect, spell(3, SpellLevel.LEVEL_2), no_cantrip_slots)
            == "the character has no spell slots of its level"
        )

    def test_schools_and_ritual(self):
        effect = open_effect(schools=[SpellSchool.ABJURATION], ritual_only=True)

        assert spell_refusal(effect, spell(1, school=SpellSchool.ABJURATION, ritual=True), ownership()) is None
        assert spell_refusal(effect, spell(2, ritual=True), ownership()) == "its school isn't one the option allows"
        assert spell_refusal(effect, spell(3, school=SpellSchool.ABJURATION), ownership()) == "it isn't a ritual"

    def test_a_spell_the_character_has_is_refused(self):
        assert spell_refusal(open_effect(), spell(1), ownership(owned=[1])) == "the character already has it"


@pytest.mark.unit
class TestAllowedSpells:
    def test_fitting_candidates_by_level_then_name(self):
        option = SimpleNamespace(spell_effects=[open_effect(max_level=SpellLevel.LEVEL_1)])
        candidates = [spell(3, SpellLevel.LEVEL_1), spell(2, SpellLevel.LEVEL_2), spell(1, SpellLevel.CANTRIP)]

        assert [s.id for s in allowed_spells(option, candidates, ownership(owned=[4]))] == [1, 3]

    def test_a_concrete_option_has_no_candidates(self):
        option = SimpleNamespace(spell_effects=[SimpleNamespace(spell_id=5)])

        assert open_spell_effect(option) is None
        assert allowed_spells(option, [spell(1)], ownership()) == []


@pytest.mark.unit
class TestSpellSources:
    def test_ownership_leaves_the_grant_itself_out(self):
        sources = SpellSources(
            castable_levels={SpellLevel.LEVEL_1},
            row_spell_ids={1},
            grant_spell_ids={10: {2}, 11: {3}},
        )

        result = sources.ownership(10, [4])

        assert result.owned == {1, 3, 4}
        assert result.castable_levels == {SpellLevel.LEVEL_1}


@pytest.mark.unit
class TestBuildSpellSources:
    def test_collects_slot_levels_row_spells_and_each_grants_spells(self):
        grants = {
            10: (object(), GrantEffects(spells={2})),
            11: (object(), GrantEffects(spells={3, 4})),
        }

        sources = build_spell_sources([SpellLevel.LEVEL_1], [1, 1], grants)

        assert sources.castable_levels == {SpellLevel.LEVEL_1}
        assert sources.row_spell_ids == {1}
        assert sources.grant_spell_ids == {10: {2}, 11: {3, 4}}

    def test_ownership_of_a_pick_counts_the_other_grants_and_rows(self):
        grants = {
            10: (object(), GrantEffects(spells={2})),
            11: (object(), GrantEffects(spells={3})),
        }
        sources = build_spell_sources([], [1], grants)

        assert sources.ownership(10, []).owned == {1, 3}
