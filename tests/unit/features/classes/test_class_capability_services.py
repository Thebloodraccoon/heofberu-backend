"""Unit tests for the class capability services: proficiencies, available skills, feature list, repository helpers."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore, ArmorProficiency, FeatureSourceType, WeaponProficiency
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.features.classes.cache import CLASS_ITEMS_CACHE_NAMESPACES
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.features.service import ClassFeatureService
from app.features.classes.items.service import ClassItemsService
from app.features.classes.proficiencies.kinds import ARMOR_PROFICIENCIES, SAVING_THROWS, WEAPON_PROFICIENCIES
from app.features.classes.proficiencies.schemas import (
    ArmorProficienciesUpdate,
    SavingThrowsUpdate,
    WeaponProficienciesUpdate,
)
from app.features.classes.proficiencies.service import ClassProficiencyService
from app.features.classes.skills.schemas import AvailableSkillsUpdate
from app.features.classes.skills.service import ClassSkillService
from app.models import ClassArmorProficiency, ClassSavingThrow, ClassWeaponProficiency
from tests.unit.fakes import FakeAsyncSession
from tests.unit.features.classes.helpers import FakeClassRepository, make_class_row, purged_namespaces


def with_fake_repository(service, db, existing_by_id):
    service.repository = FakeClassRepository(db, existing_by_id=existing_by_id)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassProficiencyService:
    @pytest.mark.parametrize(
        ("method", "payload", "kind", "values"),
        [
            (
                "set_saving_throws",
                SavingThrowsUpdate(saving_throws=[AbilityScore.STR, AbilityScore.CON]),
                SAVING_THROWS,
                [AbilityScore.STR, AbilityScore.CON],
            ),
            (
                "set_armor_proficiencies",
                ArmorProficienciesUpdate(armor_proficiencies=[ArmorProficiency.LIGHT, ArmorProficiency.SHIELD]),
                ARMOR_PROFICIENCIES,
                [ArmorProficiency.LIGHT, ArmorProficiency.SHIELD],
            ),
            (
                "set_weapon_proficiencies",
                WeaponProficienciesUpdate(weapon_proficiencies=[WeaponProficiency.SIMPLE]),
                WEAPON_PROFICIENCIES,
                [WeaponProficiency.SIMPLE],
            ),
        ],
    )
    async def test_each_list_is_replaced_through_the_generic_path(self, purged, method, payload, kind, values):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassProficiencyService(db), db, {1: make_class_row()})

        result = await getattr(service, method)(1, payload)

        assert result.id == 1
        assert service.repository.proficiency_calls == [(1, kind, values, True)]
        assert purged_namespaces(purged) == ["classes"]

    async def test_missing_class_raises_before_writing(self, purged):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassProficiencyService(db), db, {})

        with pytest.raises(RecordNotFoundError):
            await service.set_saving_throws(99, SavingThrowsUpdate(saving_throws=[]))

        assert service.repository.proficiency_calls == []
        assert purged.await_count == 0

    async def test_empty_list_clears_the_proficiency(self, purged):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassProficiencyService(db), db, {1: make_class_row()})

        await service.set_armor_proficiencies(1, ArmorProficienciesUpdate(armor_proficiencies=[]))

        assert service.repository.proficiency_calls == [(1, ARMOR_PROFICIENCIES, [], True)]


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassRepositoryProficiencies:
    @pytest.mark.parametrize(
        ("kind", "model", "column", "value"),
        [
            (SAVING_THROWS, ClassSavingThrow, "ability", AbilityScore.WIS),
            (ARMOR_PROFICIENCIES, ClassArmorProficiency, "armor_type", ArmorProficiency.HEAVY),
            (WEAPON_PROFICIENCIES, ClassWeaponProficiency, "weapon_category", WeaponProficiency.MARTIAL),
        ],
    )
    async def test_replace_deletes_then_adds_rows_of_the_right_table(self, kind, model, column, value):
        session = FakeAsyncSession()

        await ClassRepository(session).set_proficiencies(4, kind, [value])

        assert len(session.executes) == 1
        assert [type(row) for row in session.added] == [model]
        assert session.added[0].class_id == 4
        assert getattr(session.added[0], column) == value
        assert session.commits == 1

    async def test_commit_false_only_flushes(self):
        session = FakeAsyncSession()

        await ClassRepository(session).set_proficiencies(4, SAVING_THROWS, [AbilityScore.STR], commit=False)

        assert (session.flushes, session.commits) == (1, 0)

    async def test_set_available_skills_replaces_association_by_class_id(self):
        session = FakeAsyncSession()

        await ClassRepository(session).set_available_skills(4, [SimpleNamespace(id=1), SimpleNamespace(id=2)])

        assert len(session.executes) == 2
        assert session.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassSkillService:
    async def test_set_available_skills_resolves_ids_and_returns_full_class(self, purged):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassSkillService(db), db, {1: make_class_row()})
        skills = [SimpleNamespace(id=3), SimpleNamespace(id=7)]

        async def get_skills_by_ids(ids):
            return skills

        service.repository.get_skills_by_ids = get_skills_by_ids

        result = await service.set_available_skills(1, AvailableSkillsUpdate(skill_ids=[3, 7]))

        assert result.id == 1
        assert service.repository.skill_calls == [(1, skills, False)]
        assert purged_namespaces(purged) == ["classes"]

    async def test_unknown_skill_id_is_rejected(self, purged):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassSkillService(db), db, {1: make_class_row()})

        async def get_skills_by_ids(ids):
            return []

        service.repository.get_skills_by_ids = get_skills_by_ids

        with pytest.raises(RecordIdsInvalidError):
            await service.set_available_skills(1, AvailableSkillsUpdate(skill_ids=[999]))

        assert service.repository.skill_calls == []
        assert purged.await_count == 0

    async def test_empty_list_clears_skills(self, purged):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassSkillService(db), db, {1: make_class_row()})

        await service.set_available_skills(1, AvailableSkillsUpdate(skill_ids=[]))

        assert service.repository.skill_calls == [(1, None, False)]


@pytest.mark.unit
class TestClassItemsServiceCache:
    def test_items_writes_also_purge_the_shared_nested_items_listings(self):
        assert ClassItemsService.cache_namespaces == CLASS_ITEMS_CACHE_NAMESPACES == ("classes", "nested_items")


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassFeatureService:
    async def test_list_features_404s_for_unknown_class_and_reads_class_source(self):
        db = FakeAsyncSession()
        service = with_fake_repository(ClassFeatureService(db), db, {1: make_class_row()})
        calls = []

        async def list_for_source(source_type, source_id):
            calls.append((source_type, source_id))
            return []

        service._features.list_for_source = list_for_source

        assert await service.list_features(1) == []
        assert calls == [(FeatureSourceType.CLASS, 1)]

        with pytest.raises(RecordNotFoundError):
            await service.list_features(99)
