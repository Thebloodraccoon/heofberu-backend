"""
Unit tests for the central FeatureCrudService.

Covers the service bodies the integration tests through the HTTP layer do
not trace: source-scoped listing, any-source create, the level/feat-column
rules on update, the one-transaction delete with its in-use guard, the
"reconcile only on a level change" rule and the post-commit cache purge.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, FeatureSourceType
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.features.cache import SOURCE_FEATURE_LIST_NAMESPACE, feature_namespaces
from app.features.features.crud.schemas import FeatureCreate, FeatureResponse, FeatureUpdate
from app.features.features.crud.service import FeatureCrudService
from app.features.features.exceptions import InvalidFeatureSourceException
from app.models.features.feature_model import Feature
from tests.unit.fakes import FakeAsyncSession, FakeRepository

_FK_BY_SOURCE = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "subclass_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.SUBRACE: "subrace_id",
    FeatureSourceType.BACKGROUND: "background_id",
}


def make_feature(**overrides) -> SimpleNamespace:
    source_type = overrides.get("source_type", FeatureSourceType.CLASS)
    fk_name = _FK_BY_SOURCE.get(source_type)
    base = {
        "id": 1,
        "name": "Extra Attack",
        "source_type": source_type,
        "class_id": None,
        "subclass_id": None,
        "race_id": None,
        "subrace_id": None,
        "background_id": None,
        "level": 5 if fk_name is not None else None,
        "description": "",
        "min_level": None,
        "prerequisite_ability": None,
        "prerequisite_minimum_score": None,
        "prerequisite_description": "",
    }
    if fk_name is not None:
        base[fk_name] = 1
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeFeatureRepository(FakeRepository):
    """Feature repository stand-in (base fake already records create/update/delete)."""

    def __init__(self, db, existing_by_id=None, holders=(), granted=False, listed=()):
        super().__init__(db, existing_by_id=existing_by_id, model=Feature)
        self.holders = list(holders)
        self.granted = granted
        self.listed = list(listed)
        self.list_calls = []
        self.marked_empty = []

    async def get_plain(self, feature_id):
        return self._rows.get(feature_id)

    async def delete(self, db_obj, *, commit=True):
        self.deleted.append(db_obj)
        await self.commit_or_flush(commit=commit)
        return True

    def mark_effects_empty(self, feature):
        self.marked_empty.append(feature)

    async def holder_character_ids(self, feature_id):
        return self.holders

    async def is_granted(self, feature_id):
        return self.granted

    async def list_for_source(self, fk_name, source_id):
        self.list_calls.append((fk_name, source_id))
        return self.listed


@pytest.fixture(autouse=True)
def cache_spies(monkeypatch):
    """Capture the post-commit purges and the character-cache invalidation instead of touching Redis."""

    spies = SimpleNamespace(invalidate=AsyncMock(), characters=AsyncMock())
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", spies.invalidate)
    monkeypatch.setattr("app.features.features.crud.service.invalidate_characters_cache", spies.characters)
    return spies


@pytest.fixture
def reconcile(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.features.features.crud.service.reconcile_characters_for_source", mock)
    return mock


def purged_namespaces(spies) -> list[str]:
    return sorted(call.args[0] for call in spies.invalidate.call_args_list)


def make_crud_service(existing_by_id=None, execute_results=None, **repo_kwargs):
    db = FakeAsyncSession(execute_results=execute_results)
    service = FeatureCrudService(db)
    service.repository = FakeFeatureRepository(db, existing_by_id=existing_by_id, **repo_kwargs)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudCreate:
    async def test_create_other_feature(self, reconcile):
        service, db = make_crud_service()
        data = FeatureCreate(name="Gift", source_type=FeatureSourceType.OTHER, description="d")

        result = await service.create(data)

        assert result.id == 1
        assert result.name == "Gift"
        assert db.commits == 1

    async def test_create_marks_effect_collections_loaded_instead_of_refetching_the_tree(self, reconcile):
        service, _ = make_crud_service()

        await service.create(FeatureCreate(name="Gift", source_type=FeatureSourceType.OTHER))

        assert [row.name for row in service.repository.marked_empty] == ["Gift"]

    async def test_create_source_owned_feature(self, reconcile):
        service, _ = make_crud_service()
        data = FeatureCreate(name="Keen Senses", source_type=FeatureSourceType.RACE, race_id=3, description="d")

        result = await service.create(data)

        assert result.race_id == 3
        assert result.level is None

    async def test_create_source_owned_feature_reconciles_characters_before_the_commit(self, reconcile):
        service, db = make_crud_service()
        commits_seen_by_reconcile = []
        reconcile.side_effect = lambda *args: commits_seen_by_reconcile.append(db.commits)

        await service.create(
            FeatureCreate(name="Keen Senses", source_type=FeatureSourceType.RACE, race_id=3, description="d")
        )

        reconcile.assert_awaited_once_with(db, FeatureSourceType.RACE, 3)
        assert commits_seen_by_reconcile == [0]
        assert db.commits == 1

    async def test_create_other_skips_character_reconciliation(self, reconcile):
        service, _ = make_crud_service()

        await service.create(FeatureCreate(name="Gift", source_type=FeatureSourceType.OTHER, description="d"))

        reconcile.assert_not_awaited()

    async def test_create_purges_owning_catalog_list_and_parent_after_the_commit(self, reconcile, cache_spies):
        service, db = make_crud_service()
        commits_seen = []
        cache_spies.invalidate.side_effect = lambda namespace: commits_seen.append(db.commits)

        await service.create(FeatureCreate(name="Fey", source_type=FeatureSourceType.SUBRACE, subrace_id=1, level=1))

        # the shared namespace, the subrace's own list and its parent read — never a neighbor catalog
        assert SOURCE_FEATURE_LIST_NAMESPACE[FeatureSourceType.SUBRACE] == "subrace_features"
        assert purged_namespaces(cache_spies) == ["features", "races", "subrace_features"]
        assert set(commits_seen) == {1}

    async def test_failed_reconcile_rolls_back_and_purges_nothing(self, reconcile, cache_spies):
        reconcile.side_effect = RuntimeError("boom")
        service, db = make_crud_service()

        with pytest.raises(RuntimeError):
            await service.create(FeatureCreate(name="Fey", source_type=FeatureSourceType.RACE, race_id=1))

        assert db.rollbacks == 1
        assert db.commits == 0
        cache_spies.invalidate.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudListForSource:
    async def test_list_for_source_resolves_fk(self):
        rows = [make_feature(id=1, source_type=FeatureSourceType.CLASS, class_id=4, name="A", level=1)]
        service, _ = make_crud_service(listed=rows)

        result = await service.list_for_source(FeatureSourceType.CLASS, 4)

        assert [item.name for item in result] == ["A"]
        assert service.repository.list_calls == [("class_id", 4)]

    async def test_list_for_source_other_raises(self):
        service, _ = make_crud_service()

        with pytest.raises(ValueError):
            await service.list_for_source(FeatureSourceType.OTHER, 1)


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudUpdate:
    async def test_update_renames_feature(self, reconcile):
        feature = make_feature()
        service, _ = make_crud_service(existing_by_id={1: feature})

        result = await service.update_feature(1, FeatureUpdate(name="Legendary Action"))

        assert result.name == "Legendary Action"

    async def test_update_level_out_of_range_rejected(self):
        feature = make_feature()
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException):
            await service.update_feature(1, FeatureUpdate(level=25))

    async def test_update_level_zero_rejected_for_race_features_too(self):
        feature = make_feature(source_type=FeatureSourceType.RACE, race_id=2, level=1)
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException, match="between 1 and 20"):
            await service.update_feature(1, FeatureUpdate(level=0))

    async def test_update_class_level_cannot_be_cleared(self):
        feature = make_feature(source_type=FeatureSourceType.CLASS)
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException):
            await service.update_feature(1, FeatureUpdate(level=None))

    async def test_update_race_level_optional_and_clearable(self, reconcile):
        feature = make_feature(source_type=FeatureSourceType.RACE, race_id=2, level=1)
        service, _ = make_crud_service(existing_by_id={1: feature})

        result = await service.update_feature(1, FeatureUpdate(level=None))

        assert result.level is None

    async def test_update_feat_cannot_get_a_level(self):
        feature = make_feature(source_type=FeatureSourceType.FEAT)
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException, match="FEAT features do not use 'level'"):
            await service.update_feature(1, FeatureUpdate(level=4))

    @pytest.mark.parametrize(
        "fields",
        [
            {"min_level": 4},
            {"prerequisite_description": "Needs magic"},
            {"prerequisite_ability": AbilityScore.STR, "prerequisite_minimum_score": 13},
        ],
    )
    async def test_update_non_feat_rejects_feat_only_columns(self, fields):
        feature = make_feature(source_type=FeatureSourceType.OTHER)
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException, match="only valid for FEAT"):
            await service.update_feature(1, FeatureUpdate(**fields))

    async def test_update_feat_prerequisite_pair_is_checked_against_the_stored_row(self):
        feature = make_feature(source_type=FeatureSourceType.FEAT)
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException, match="must be set together"):
            await service.update_feature(1, FeatureUpdate(prerequisite_ability=AbilityScore.STR))

    async def test_unrelated_patch_of_a_legacy_feat_with_half_a_prerequisite_is_not_blocked(self, cache_spies):
        feature = make_feature(source_type=FeatureSourceType.FEAT, prerequisite_ability=AbilityScore.STR)
        service, _ = make_crud_service(existing_by_id={1: feature})

        result = await service.update_feature(1, FeatureUpdate(description="Edited"))

        assert result.description == "Edited"

    async def test_update_feat_prerequisite_pair_accepted_when_the_other_half_is_stored(self, cache_spies):
        feature = make_feature(source_type=FeatureSourceType.FEAT, prerequisite_ability=AbilityScore.STR)
        feature.prerequisite_minimum_score = 13
        service, _ = make_crud_service(existing_by_id={1: feature})

        result = await service.update_feature(1, FeatureUpdate(prerequisite_minimum_score=15))

        assert result.prerequisite_minimum_score == 15

    async def test_level_change_reconciles_owning_source_characters_in_the_same_transaction(self, reconcile):
        service, db = make_crud_service(existing_by_id={1: make_feature()})
        commits_seen = []
        reconcile.side_effect = lambda *args: commits_seen.append(db.commits)

        await service.update_feature(1, FeatureUpdate(level=3))

        reconcile.assert_awaited_once_with(db, FeatureSourceType.CLASS, 1)
        assert commits_seen == [0]
        assert db.commits == 1

    async def test_description_only_change_does_not_reconcile_characters(self, reconcile, cache_spies):
        service, db = make_crud_service(existing_by_id={1: make_feature()}, holders=[7, 8])

        await service.update_feature(1, FeatureUpdate(description="New text"))

        reconcile.assert_not_awaited()
        assert db.commits == 1
        # holders' cached payloads embed the description, so only THEY are purged
        cache_spies.characters.assert_awaited_once_with([7, 8])

    async def test_name_change_does_not_reconcile_characters(self, reconcile):
        service, _ = make_crud_service(existing_by_id={1: make_feature()})

        await service.update_feature(1, FeatureUpdate(name="Renamed"))

        reconcile.assert_not_awaited()

    async def test_unchanged_level_does_not_reconcile(self, reconcile):
        service, _ = make_crud_service(existing_by_id={1: make_feature(level=5)})

        await service.update_feature(1, FeatureUpdate(level=5, description="x"))

        reconcile.assert_not_awaited()

    async def test_no_op_patch_commits_nothing_and_purges_nothing(self, reconcile, cache_spies):
        service, db = make_crud_service(existing_by_id={1: make_feature(name="Same")})

        result = await service.update_feature(1, FeatureUpdate(name="Same"))

        assert result.name == "Same"
        assert db.commits == 0
        reconcile.assert_not_awaited()
        cache_spies.invalidate.assert_not_awaited()

    async def test_update_purges_feature_caches_after_commit(self, reconcile, cache_spies):
        service, db = make_crud_service(existing_by_id={1: make_feature(source_type=FeatureSourceType.CLASS)})
        commits_seen = []
        cache_spies.invalidate.side_effect = lambda namespace: commits_seen.append(db.commits)

        await service.update_feature(1, FeatureUpdate(level=2))

        assert purged_namespaces(cache_spies) == sorted(feature_namespaces(FeatureSourceType.CLASS))
        assert set(commits_seen) == {1}

    async def test_update_raises_when_feature_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.update_feature(99, FeatureUpdate(name="x"))


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudDelete:
    async def test_delete_source_owned_feature_is_one_transaction_with_reconcile_before_the_commit(
        self, reconcile, cache_spies
    ):
        feature = make_feature(source_type=FeatureSourceType.BACKGROUND, background_id=7)
        service, db = make_crud_service(existing_by_id={1: feature})
        seen = []
        reconcile.side_effect = lambda *args: seen.append(("reconcile", db.commits))
        cache_spies.invalidate.side_effect = lambda namespace: seen.append(("purge", db.commits))

        result = await service.delete(1)

        assert result is True
        assert service.repository.deleted == [feature]
        reconcile.assert_awaited_once_with(db, FeatureSourceType.BACKGROUND, 7)
        assert db.commits == 1
        assert seen[0] == ("reconcile", 0)
        assert all(entry == ("purge", 1) for entry in seen[1:])

    async def test_failed_reconcile_rolls_the_delete_back_and_purges_nothing(self, reconcile, cache_spies):
        reconcile.side_effect = RuntimeError("boom")
        service, db = make_crud_service(existing_by_id={1: make_feature()})

        with pytest.raises(RuntimeError):
            await service.delete(1)

        assert db.rollbacks == 1
        assert db.commits == 0
        cache_spies.invalidate.assert_not_awaited()

    @pytest.mark.parametrize("source_type", [FeatureSourceType.FEAT, FeatureSourceType.OTHER])
    async def test_standalone_feature_held_by_characters_cannot_be_deleted(self, source_type, reconcile, cache_spies):
        feature = make_feature(source_type=source_type)
        service, db = make_crud_service(existing_by_id={1: feature}, granted=True)

        with pytest.raises(RecordInUseError):
            await service.delete(1)

        assert service.repository.deleted == []
        assert db.commits == 0
        cache_spies.invalidate.assert_not_awaited()

    async def test_unheld_standalone_feature_is_deleted_without_reconcile(self, reconcile, cache_spies):
        feature = make_feature(source_type=FeatureSourceType.FEAT)
        service, db = make_crud_service(existing_by_id={1: feature}, granted=False)

        assert await service.delete(1) is True

        reconcile.assert_not_awaited()
        assert db.commits == 1
        assert purged_namespaces(cache_spies) == ["feats", "features"]

    async def test_delete_raises_when_feature_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(99)


@pytest.mark.unit
class TestFeatureStaticEffectsSerialization:
    """Verify that FeatureResponse serializes static_groups (the discriminated effect groups)."""

    def test_feature_response_serializes_static_groups(self):
        feature = SimpleNamespace(
            id=1,
            name="Primal Champion",
            source_type=FeatureSourceType.CLASS,
            class_id=1,
            subclass_id=None,
            race_id=None,
            subrace_id=None,
            background_id=None,
            level=20,
            description="You embrace the primal power.",
            static_groups=[
                {
                    "effect_type": "ability",
                    "items": [
                        SimpleNamespace(ability=AbilityScore.STR, amount=4, new_cap=None),
                        SimpleNamespace(ability=AbilityScore.CON, amount=4, new_cap=None),
                    ],
                }
            ],
        )

        response = FeatureResponse.model_validate(feature)

        items = response.static_groups[0].items
        assert len(items) == 2
        assert items[0].ability == AbilityScore.STR
        assert items[0].amount == 4
        assert items[1].ability == AbilityScore.CON
        assert items[1].amount == 4

    def test_feature_response_empty_static_groups_by_default(self):
        feature = SimpleNamespace(
            id=2,
            name="Extra Attack",
            source_type=FeatureSourceType.CLASS,
            class_id=1,
            subclass_id=None,
            race_id=None,
            subrace_id=None,
            background_id=None,
            level=5,
            description="",
        )

        response = FeatureResponse.model_validate(feature)

        assert response.static_groups == []
