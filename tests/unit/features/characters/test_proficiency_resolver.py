"""Unit tests for the single proficiency resolver (GM REVOKE veto, expertise precedence, grouping)."""

from types import SimpleNamespace

import pytest

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType, SkillEffectMode
from app.features.characters.grants.effects import GrantEffects, SkillClaim
from app.features.characters.proficiencies.resolver import (
    feature_entries,
    proficiency_key,
    resolve_all,
    resolve_group,
    row_entry,
    row_key,
)

SKILL = ProficiencyType.SKILL


def make_row(source_type, *, skill_id=1, action=ProficiencyAction.GRANT, is_expertise=False, actor_user_id=None):
    return SimpleNamespace(
        proficiency_type=SKILL,
        skill_id=skill_id,
        ability=None,
        armor_type=None,
        weapon_category=None,
        item_id=None,
        source_type=source_type,
        action=action,
        is_expertise=is_expertise,
        actor_user_id=actor_user_id,
    )


def make_feature(feature_id=7):
    return SimpleNamespace(id=feature_id, name="Nimble", source_type="CLASS")


def resolve_skill(*entries, skill_id=1):
    return resolve_group((SKILL, skill_id), list(entries))


def claim(*modes: SkillEffectMode) -> SkillClaim:
    folded = SkillClaim()
    for mode in modes:
        folded.add(mode)
    return folded


def skill_grant(*modes: SkillEffectMode, feature_id=7):
    """The entries of a feature grant whose skill effects in skill 1 have ``modes``."""

    return feature_entries(make_feature(feature_id), GrantEffects(skills={1: claim(*modes)}))


PROFICIENCY = SkillEffectMode.PROFICIENCY
BOTH = SkillEffectMode.PROFICIENCY_AND_EXPERTISE
EXPERTISE = SkillEffectMode.EXPERTISE
UPGRADE = SkillEffectMode.UPGRADE


@pytest.mark.unit
class TestKeys:
    def test_keyword_discriminator_matches_the_row_key(self):
        row = make_row(ProficiencySourceType.CLASS_CHOICE, skill_id=4)

        assert proficiency_key(SKILL, skill_id=4) == row_key(row)

    def test_weapon_key_carries_both_columns(self):
        assert proficiency_key(ProficiencyType.WEAPON, weapon_category="MARTIAL", item_id=None) == (
            ProficiencyType.WEAPON,
            "MARTIAL",
            None,
        )


    def test_armor_key_is_category_or_item(self):
        assert proficiency_key(ProficiencyType.ARMOR, armor_type="LIGHT", item_id=None) == (
            ProficiencyType.ARMOR,
            "LIGHT",
            None,
        )
        assert proficiency_key(ProficiencyType.ARMOR, armor_type=None, item_id=40) == (
            ProficiencyType.ARMOR,
            None,
            40,
        )

    def test_armor_row_key_carries_both_columns(self):
        row = SimpleNamespace(
            proficiency_type=ProficiencyType.ARMOR,
            armor_type=None,
            item_id=40,
            weapon_category=None,
            skill_id=None,
            ability=None,
        )

        assert row_key(row) == (ProficiencyType.ARMOR, None, 40)

    def test_item_armor_effect_yields_item_key(self):
        entries = feature_entries(make_feature(), GrantEffects(armor={(None, 40)}))

        assert [entry.key for entry in entries] == [(ProficiencyType.ARMOR, None, 40)]


@pytest.mark.unit
class TestResolveGroup:
    def test_no_entries_means_not_proficient(self):
        assert resolve_skill() is None

    def test_any_stored_row_grants(self):
        resolved = resolve_skill(row_entry(make_row(ProficiencySourceType.CLASS_CHOICE)))

        assert resolved is not None
        assert resolved.is_expertise is False
        assert [source.source_type for source in resolved.sources] == [ProficiencySourceType.CLASS_CHOICE]

    def test_feature_grant_alone_grants_and_is_tagged_with_its_feature(self):
        entries = skill_grant(BOTH)

        resolved = resolve_skill(*entries)

        assert resolved is not None
        assert resolved.is_expertise is True
        assert resolved.sources[0].feature_id == 7
        assert resolved.sources[0].source_type == ProficiencySourceType.FEATURE

    def test_gm_revoke_vetoes_every_other_source(self):
        resolved = resolve_skill(
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE)),
            *skill_grant(PROFICIENCY),
            row_entry(make_row(ProficiencySourceType.GM, action=ProficiencyAction.REVOKE, is_expertise=None)),
        )

        assert resolved is None

    def test_expertise_is_the_or_of_sources_without_an_explicit_gm_decision(self):
        resolved = resolve_skill(
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE, is_expertise=False)),
            *skill_grant(BOTH),
            row_entry(make_row(ProficiencySourceType.GM, is_expertise=None)),
        )

        assert resolved.is_expertise is True

    def test_explicit_gm_false_clears_expertise_another_source_gives(self):
        resolved = resolve_skill(
            *skill_grant(BOTH),
            row_entry(make_row(ProficiencySourceType.GM, is_expertise=False)),
        )

        assert resolved is not None
        assert resolved.is_expertise is False

    def test_explicit_gm_true_grants_expertise_over_plain_sources(self):
        resolved = resolve_skill(
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE, is_expertise=False)),
            row_entry(make_row(ProficiencySourceType.GM, is_expertise=True)),
        )

        assert resolved.is_expertise is True

    def test_gm_row_is_flagged_as_gm_entry(self):
        assert row_entry(make_row(ProficiencySourceType.GM)).is_gm
        assert not row_entry(make_row(ProficiencySourceType.RACE)).is_gm


@pytest.mark.unit
class TestResolveAll:
    def test_groups_by_proficiency_and_drops_revoked_ones(self):
        entries = [
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE, skill_id=1)),
            row_entry(make_row(ProficiencySourceType.RACE, skill_id=1)),
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE, skill_id=2)),
            row_entry(make_row(ProficiencySourceType.GM, skill_id=2, action=ProficiencyAction.REVOKE)),
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE, skill_id=3)),
        ]

        resolved = {proficiency.key: proficiency for proficiency in resolve_all(entries)}

        assert set(resolved) == {(SKILL, 1), (SKILL, 3)}
        assert len(resolved[(SKILL, 1)].sources) == 2

    def test_feature_entries_cover_every_proficiency_kind(self):
        effects = GrantEffects(
            skills={1: claim(PROFICIENCY)},
            saving_throws={"CON"},
            armor={("LIGHT", None), (None, 40)},
            weapons={("MARTIAL", None), (None, 9)},
        )

        keys = {entry.key for entry in feature_entries(make_feature(), effects)}

        assert keys == {
            (SKILL, 1),
            (ProficiencyType.SAVING_THROW, "CON"),
            (ProficiencyType.ARMOR, "LIGHT", None),
            (ProficiencyType.ARMOR, None, 40),
            (ProficiencyType.WEAPON, "MARTIAL", None),
            (ProficiencyType.WEAPON, None, 9),
        }


@pytest.mark.unit
class TestSkillEffectModes:
    def test_expertise_only_without_another_source_gives_nothing(self):
        assert resolve_skill(*skill_grant(EXPERTISE)) is None

    def test_expertise_only_on_top_of_a_stored_proficiency_is_expertise(self):
        resolved = resolve_skill(row_entry(make_row(ProficiencySourceType.CLASS_CHOICE)), *skill_grant(EXPERTISE))

        assert resolved is not None
        assert resolved.is_expertise is True
        assert len(resolved.sources) == 2

    def test_expertise_only_is_cleared_by_an_explicit_gm_false(self):
        resolved = resolve_skill(
            row_entry(make_row(ProficiencySourceType.CLASS_CHOICE)),
            row_entry(make_row(ProficiencySourceType.GM, is_expertise=False)),
            *skill_grant(EXPERTISE),
        )

        assert resolved is not None
        assert resolved.is_expertise is False

    def test_upgrade_alone_is_plain_proficiency(self):
        resolved = resolve_skill(*skill_grant(UPGRADE))

        assert resolved is not None
        assert resolved.is_expertise is False

    def test_upgrade_with_another_source_becomes_expertise(self):
        resolved = resolve_skill(row_entry(make_row(ProficiencySourceType.BACKGROUND)), *skill_grant(UPGRADE))

        assert resolved is not None
        assert resolved.is_expertise is True

    def test_two_upgrades_from_different_grants_make_expertise(self):
        resolved = resolve_skill(*skill_grant(UPGRADE, feature_id=7), *skill_grant(UPGRADE, feature_id=8))

        assert resolved is not None
        assert resolved.is_expertise is True

    def test_expertise_only_on_an_upgrades_own_proficiency_is_expertise(self):
        resolved = resolve_skill(*skill_grant(UPGRADE, feature_id=7), *skill_grant(EXPERTISE, feature_id=8))

        assert resolved is not None
        assert resolved.is_expertise is True
