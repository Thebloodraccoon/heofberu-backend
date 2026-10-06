"""Unit tests for CharacterProficiencyGmRepository: the upsert-and-clear rule and the targeted feature-grant query."""

import pytest
from sqlalchemy.dialects import postgresql

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.features.characters.gm_panel.proficiencies.repository import CharacterProficiencyGmRepository
from app.models.character.character_proficiency_model import CharacterProficiency
from tests.unit.fakes import FakeAsyncSession, FakeResult

SKILL = ProficiencyType.SKILL


def gm_row(action=ProficiencyAction.GRANT, is_expertise=None):
    return CharacterProficiency(
        character_id=1,
        proficiency_type=SKILL,
        skill_id=1,
        source_type=ProficiencySourceType.GM,
        action=action,
        is_expertise=is_expertise,
    )


async def apply(rows, *, granted, others_grant, is_expertise=None):
    db = FakeAsyncSession()
    repository = CharacterProficiencyGmRepository(db)
    result = await repository.apply(
        1,
        SKILL,
        rows,
        granted=granted,
        others_grant=others_grant,
        actor_user_id=9,
        is_expertise=is_expertise,
        skill_id=1,
    )
    return db, result


@pytest.mark.unit
@pytest.mark.asyncio
class TestApply:
    async def test_grant_with_no_other_source_inserts_a_grant_row(self):
        db, row = await apply([], granted=True, others_grant=False)

        assert db.added == [row]
        assert (row.action, row.actor_user_id, row.is_expertise) == (ProficiencyAction.GRANT, 9, None)
        assert row.source_type == ProficiencySourceType.GM
        assert db.flushes == 1
        assert db.commits == 0

    async def test_grant_that_another_source_already_gives_needs_no_row(self):
        db, row = await apply([], granted=True, others_grant=True)

        assert row is None
        assert db.added == []
        assert db.flushes == 0

    async def test_revoke_of_another_sources_proficiency_inserts_a_veto(self):
        db, row = await apply([], granted=False, others_grant=True)

        assert row.action == ProficiencyAction.REVOKE
        assert row.is_expertise is None

    async def test_revoke_of_a_gm_only_grant_deletes_it(self):
        existing = gm_row()
        db, row = await apply([existing], granted=False, others_grant=False)

        assert row is None
        assert db.deleted == [existing]

    async def test_grant_over_a_veto_with_other_sources_deletes_the_veto(self):
        existing = gm_row(ProficiencyAction.REVOKE)
        db, row = await apply([existing], granted=True, others_grant=True)

        assert row is None
        assert db.deleted == [existing]

    async def test_grant_over_a_veto_without_other_sources_flips_it_to_a_grant(self):
        existing = gm_row(ProficiencyAction.REVOKE)
        db, row = await apply([existing], granted=True, others_grant=False)

        assert row is existing
        assert existing.action == ProficiencyAction.GRANT
        assert db.deleted == []
        assert db.added == []

    async def test_revoke_over_a_gm_grant_with_other_sources_flips_it_to_a_veto_and_drops_expertise(self):
        existing = gm_row(ProficiencyAction.GRANT, is_expertise=True)
        db, row = await apply([existing], granted=False, others_grant=True)

        assert row is existing
        assert (existing.action, existing.is_expertise) == (ProficiencyAction.REVOKE, None)

    async def test_explicit_expertise_always_keeps_a_grant_row(self):
        db, row = await apply([], granted=True, others_grant=True, is_expertise=False)

        assert (row.action, row.is_expertise) == (ProficiencyAction.GRANT, False)

    async def test_other_sources_rows_are_never_touched(self):
        class_row = CharacterProficiency(
            character_id=1,
            proficiency_type=SKILL,
            skill_id=1,
            source_type=ProficiencySourceType.CLASS_CHOICE,
            action=ProficiencyAction.GRANT,
        )

        db, row = await apply([class_row], granted=False, others_grant=True)

        assert class_row.action == ProficiencyAction.GRANT
        assert db.deleted == []
        assert row.source_type == ProficiencySourceType.GM


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureEntries:
    async def test_one_query_returns_one_entry_per_granting_feature_with_summed_expertise(self):
        db = FakeAsyncSession(
            execute_results=[
                FakeResult([(7, "Nimble", "CLASS", False), (7, "Nimble", "CLASS", True), (8, "Lucky", "FEAT", False)])
            ]
        )

        entries = await CharacterProficiencyGmRepository(db).feature_entries(1, SKILL, skill_id=4)

        assert len(db.executes) == 1
        by_feature = {entry.source.feature_id: entry for entry in entries}
        assert set(by_feature) == {7, 8}
        assert by_feature[7].is_expertise is True
        assert by_feature[8].is_expertise is False
        assert by_feature[7].key == (SKILL, 4)
        assert by_feature[7].source.source_type == ProficiencySourceType.FEATURE
        assert by_feature[7].source.feature_name == "Nimble"

    async def test_query_covers_fixed_and_picked_effects_for_just_this_key(self):
        db = FakeAsyncSession(execute_results=[FakeResult([])])

        assert await CharacterProficiencyGmRepository(db).feature_entries(1, SKILL, skill_id=4) == []

        sql = str(db.executes[0].compile(dialect=postgresql.dialect()))
        assert "UNION ALL" in sql
        assert "feature_skill_proficiency_effects.skill_id" in sql
        assert "character_feature_choices" in sql
        assert "character_features.character_id" in sql
