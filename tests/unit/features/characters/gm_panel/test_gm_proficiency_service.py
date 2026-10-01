"""Unit tests for GmPanelProficiencyService: GM layer upsert/clear, re-grant after REVOKE, expertise precedence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest

from app.constants import AbilityScore, ProficiencyAction, ProficiencySourceType, ProficiencyType, WeaponProficiency
from app.core.exceptions import RecordNotFoundError
from app.features.characters.gm_panel.exceptions import (
    ProficiencyAlreadyGrantedException,
    ProficiencyNotFoundException,
    SkillProficiencyNotFoundException,
)
from app.features.characters.gm_panel.proficiencies.schemas import SkillExpertiseUpdate, WeaponProficiencyAdd
from app.features.characters.gm_panel.proficiencies.service import GmPanelProficiencyService
from app.features.characters.grants.effects import GrantEffects
from app.features.characters.proficiencies.resolver import feature_entries
from app.features.items.exceptions import ItemNotFoundException
from app.models.character.character_proficiency_model import CharacterProficiency
from tests.unit.fakes import FakeAsyncSession

GM = SimpleNamespace(id=9)
SKILL = ProficiencyType.SKILL


def make_row(source_type, *, action=ProficiencyAction.GRANT, is_expertise=None, skill_id=1):
    return CharacterProficiency(
        character_id=1,
        proficiency_type=SKILL,
        skill_id=skill_id,
        source_type=source_type,
        action=action,
        is_expertise=is_expertise,
    )


def feature_entry(*, expertise=False):
    feature = SimpleNamespace(id=7, name="Nimble", source_type="CLASS")
    return feature_entries(feature, GrantEffects(skills={1: expertise}))


def make_service(*, rows=(), features=(), skill_exists=True, item_exists=True):
    db = FakeAsyncSession()
    service = GmPanelProficiencyService(db)
    service.get_character_for_user = AsyncMock(return_value=SimpleNamespace(id=1))
    service.skill_repository = SimpleNamespace(exists_by_id=AsyncMock(return_value=skill_exists))
    service.item_repository = SimpleNamespace(exists_by_id=AsyncMock(return_value=item_exists))
    service.proficiency_repository.get_rows = AsyncMock(return_value=list(rows))
    service.proficiency_repository.feature_entries = AsyncMock(return_value=list(features))
    return service, db


@pytest.fixture(autouse=True)
def invalidate(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr("app.features.characters.gm_panel.proficiencies.service.invalidate_character_cache", mock)
    return mock


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddSkill:
    async def test_inserts_a_gm_grant_row_without_explicit_expertise(self, invalidate):
        service, db = make_service()

        result = await service.add_skill(1, 1, GM)

        (row,) = db.added
        assert row.source_type == ProficiencySourceType.GM
        assert row.action == ProficiencyAction.GRANT
        assert row.actor_user_id == 9
        assert row.is_expertise is None
        assert (result.skill_id, result.is_expertise) == (1, False)
        assert db.commits == 1
        invalidate.assert_awaited_once_with(1)

    async def test_loads_rows_and_feature_grants_once_per_operation(self):
        service, _ = make_service()

        await service.add_skill(1, 1, GM)

        service.proficiency_repository.get_rows.assert_awaited_once()
        service.proficiency_repository.feature_entries.assert_awaited_once()

    async def test_already_proficient_from_another_source_is_a_conflict_and_writes_nothing(self, invalidate):
        service, db = make_service(rows=[make_row(ProficiencySourceType.CLASS_CHOICE)])

        with pytest.raises(ProficiencyAlreadyGrantedException):
            await service.add_skill(1, 1, GM)

        assert db.added == []
        assert db.commits == 0
        invalidate.assert_not_awaited()

    async def test_already_proficient_through_a_feature_is_a_conflict(self):
        service, _ = make_service(features=feature_entry())

        with pytest.raises(ProficiencyAlreadyGrantedException):
            await service.add_skill(1, 1, GM)

    async def test_unknown_skill_is_a_404_not_a_foreign_key_error(self):
        service, db = make_service(skill_exists=False)

        with pytest.raises(RecordNotFoundError):
            await service.add_skill(1, 99, GM)

        assert db.commits == 0

    async def test_regrant_after_revoke_over_a_feature_clears_the_veto_and_still_answers(self):
        revoke = make_row(ProficiencySourceType.GM, action=ProficiencyAction.REVOKE)
        service, db = make_service(rows=[revoke], features=feature_entry())

        result = await service.add_skill(1, 1, GM)

        assert db.deleted == [revoke]
        assert db.added == []
        assert (result.skill_id, result.is_expertise) == (1, False)
        assert db.commits == 1

    async def test_regrant_reports_expertise_the_feature_gives(self):
        revoke = make_row(ProficiencySourceType.GM, action=ProficiencyAction.REVOKE)
        service, _ = make_service(rows=[revoke], features=feature_entry(expertise=True))

        result = await service.add_skill(1, 1, GM)

        assert result.is_expertise is True

    async def test_regrant_after_revoke_whose_source_is_gone_turns_the_veto_into_a_grant(self):
        revoke = make_row(ProficiencySourceType.GM, action=ProficiencyAction.REVOKE)
        service, db = make_service(rows=[revoke])

        result = await service.add_skill(1, 1, GM)

        assert revoke.action == ProficiencyAction.GRANT
        assert revoke.actor_user_id == 9
        assert db.deleted == []
        assert db.added == []
        assert result.skill_id == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveSkill:
    async def test_gm_only_grant_is_deleted(self, invalidate):
        grant = make_row(ProficiencySourceType.GM)
        service, db = make_service(rows=[grant])

        await service.remove_skill(1, 1, GM)

        assert db.deleted == [grant]
        assert db.added == []
        invalidate.assert_awaited_once_with(1)

    async def test_other_source_gets_a_revoke_row(self):
        service, db = make_service(rows=[make_row(ProficiencySourceType.CLASS_CHOICE)])

        await service.remove_skill(1, 1, GM)

        (row,) = db.added
        assert row.action == ProficiencyAction.REVOKE
        assert row.is_expertise is None

    async def test_gm_grant_over_another_source_flips_to_revoke_instead_of_vanishing(self):
        grant = make_row(ProficiencySourceType.GM)
        service, db = make_service(rows=[grant, make_row(ProficiencySourceType.CLASS_CHOICE)])

        await service.remove_skill(1, 1, GM)

        assert grant.action == ProficiencyAction.REVOKE
        assert db.deleted == []

    async def test_feature_only_skill_gets_a_revoke_row(self):
        service, db = make_service(features=feature_entry())

        await service.remove_skill(1, 1, GM)

        assert db.added[0].action == ProficiencyAction.REVOKE

    async def test_not_proficient_is_a_404(self):
        service, db = make_service()

        with pytest.raises(SkillProficiencyNotFoundException):
            await service.remove_skill(1, 1, GM)

        assert db.commits == 0

    async def test_already_revoked_is_a_404(self):
        service, _ = make_service(
            rows=[make_row(ProficiencySourceType.GM, action=ProficiencyAction.REVOKE)], features=feature_entry()
        )

        with pytest.raises(SkillProficiencyNotFoundException):
            await service.remove_skill(1, 1, GM)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetSkillExpertise:
    async def test_gm_can_clear_expertise_another_source_gives(self):
        service, db = make_service(features=feature_entry(expertise=True))

        result = await service.set_skill_expertise(1, 1, SkillExpertiseUpdate(is_expertise=False), GM)

        (row,) = db.added
        assert row.action == ProficiencyAction.GRANT
        assert row.is_expertise is False
        assert result.is_expertise is False

    async def test_gm_can_grant_expertise_on_a_class_skill(self):
        service, db = make_service(rows=[make_row(ProficiencySourceType.CLASS_CHOICE, is_expertise=False)])

        result = await service.set_skill_expertise(1, 1, SkillExpertiseUpdate(is_expertise=True), GM)

        assert db.added[0].is_expertise is True
        assert result.is_expertise is True

    async def test_updates_the_existing_gm_row_in_place(self):
        grant = make_row(ProficiencySourceType.GM, is_expertise=False)
        service, db = make_service(rows=[grant])

        result = await service.set_skill_expertise(1, 1, SkillExpertiseUpdate(is_expertise=True), GM)

        assert grant.is_expertise is True
        assert db.added == []
        assert result.is_expertise is True

    async def test_requires_proficiency(self):
        service, db = make_service()

        with pytest.raises(SkillProficiencyNotFoundException):
            await service.set_skill_expertise(1, 1, SkillExpertiseUpdate(is_expertise=True), GM)

        assert db.commits == 0

    async def test_revoked_skill_is_not_proficient(self):
        service, _ = make_service(
            rows=[make_row(ProficiencySourceType.GM, action=ProficiencyAction.REVOKE)], features=feature_entry()
        )

        with pytest.raises(SkillProficiencyNotFoundException):
            await service.set_skill_expertise(1, 1, SkillExpertiseUpdate(is_expertise=True), GM)


@pytest.mark.unit
@pytest.mark.asyncio
class TestOtherKinds:
    async def test_saving_throw_add_and_response(self):
        service, db = make_service()

        result = await service.add_saving_throw(1, AbilityScore.WIS, GM)

        assert result.ability == AbilityScore.WIS
        assert db.added[0].ability == AbilityScore.WIS
        service.proficiency_repository.get_rows.assert_awaited_once_with(
            1, ProficiencyType.SAVING_THROW, ability=AbilityScore.WIS
        )

    async def test_saving_throw_remove_missing_is_404(self):
        service, _ = make_service()

        with pytest.raises(ProficiencyNotFoundException):
            await service.remove_saving_throw(1, AbilityScore.WIS, GM)

    async def test_weapon_category_add(self):
        service, db = make_service()

        result = await service.add_weapon(1, GM, weapon_category=WeaponProficiency.MARTIAL, item_id=None)

        assert (result.weapon_category, result.item_id) == (WeaponProficiency.MARTIAL, None)
        assert db.added[0].weapon_category == WeaponProficiency.MARTIAL

    async def test_weapon_item_add_checks_the_item_exists(self):
        service, db = make_service(item_exists=False)

        with pytest.raises(ItemNotFoundException):
            await service.add_weapon(1, GM, weapon_category=None, item_id=99)

        assert db.commits == 0

    async def test_weapon_remove_missing_names_the_target(self):
        service, _ = make_service()

        with pytest.raises(ProficiencyNotFoundException) as exc_info:
            await service.remove_weapon(1, GM, weapon_category=None, item_id=5)

        assert "item 5" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
class TestTransactionBoundary:
    async def test_failed_write_rolls_back_and_skips_cache_invalidation(self, invalidate):
        service, db = make_service()
        service.proficiency_repository.apply = AsyncMock(side_effect=RuntimeError("flush failed"))

        with pytest.raises(RuntimeError):
            await service.add_skill(1, 1, GM)

        assert db.commits == 0
        assert db.rollbacks == 1
        invalidate.assert_not_awaited()


@pytest.mark.unit
class TestSchemas:
    def test_weapon_add_requires_exactly_one_target(self):
        with pytest.raises(ValidationError):
            WeaponProficiencyAdd()
        with pytest.raises(ValidationError):
            WeaponProficiencyAdd(weapon_category="MARTIAL", item_id=1)

    def test_weapon_add_accepts_either_target(self):
        assert WeaponProficiencyAdd(weapon_category="MARTIAL").item_id is None
        assert WeaponProficiencyAdd(item_id=3).weapon_category is None

    def test_non_positive_ids_are_rejected(self):
        with pytest.raises(ValidationError):
            WeaponProficiencyAdd(item_id=0)
