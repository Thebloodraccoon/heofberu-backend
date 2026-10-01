"""Unit tests for GmPanelFeatService: grant/update/revoke feat grants on a character."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, ASILevelChoice, GrantSource
from app.features.characters.feats.exceptions import (
    CharacterFeatAlreadyKnownException,
    FeatAsiChoiceRequiredException,
    FeatPrerequisiteNotMetException,
)
from app.features.characters.gm_panel.exceptions import CharacterFeatNotFoundException
from app.features.characters.gm_panel.feats.schemas import CharacterFeatAdd, CharacterFeatUpdate
from app.features.characters.gm_panel.feats.service import GmPanelFeatService
from app.features.feats.exceptions import FeatNotFoundException
from app.models.character.character_model import Character
from tests.unit.fakes import FakeAsyncSession
from tests.unit.features.characters.conftest import make_feat_with_choice_groups as make_feat


def make_character(**overrides) -> Character:
    base = {
        "id": 1,
        "owner_id": 1,
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "level": 5,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 8,
        "wisdom": 9,
        "charisma": 11,
    }
    base.update(overrides)
    return Character(**base)


def make_choice(ability_score_increase_id: int) -> SimpleNamespace:
    """A fake ``CharacterFeatureChoice`` row picking an ASI option, for ``build_chosen_options``."""

    return SimpleNamespace(
        choice_group_id=1,
        choice_option_id=1,
        choice_option=SimpleNamespace(
            ability_effects=[SimpleNamespace(id=ability_score_increase_id, ability=AbilityScore.STR, amount=1)],
            skill_effects=[],
            saving_throw_effects=[],
            armor_effects=[],
            weapon_effects=[],
            spell_effects=[],
        ),
    )


def make_grant(grant_id: int, feat_id: int, ability_score_increase_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=grant_id,
        character_id=1,
        feature_id=feat_id,
        grant_source=GrantSource.GM,
        choices=[make_choice(ability_score_increase_id)] if ability_score_increase_id is not None else [],
        feature=SimpleNamespace(id=feat_id, name="Tough", description="", effects_summary=""),
    )


TOTALS = {
    "strength_total": 14,
    "dexterity_total": 10,
    "constitution_total": 12,
    "intelligence_total": 8,
    "wisdom_total": 9,
    "charisma_total": 11,
}


class FakeStatsService:
    """Stands in for CharacterStatsService with precomputed totals/caps."""

    def __init__(self, totals=None, caps=None):
        self.totals = totals or dict(TOTALS)
        self.caps = caps if caps is not None else dict.fromkeys(AbilityScore, 20)
        self.refresh_calls = []
        self.refresh_commits = []
        self.refresh_error = None

    async def refresh(self, character, *, commit=True):
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refresh_calls.append(character)
        self.refresh_commits.append(commit)

    async def compute(self, character):
        return self.totals

    async def resolve_ability_caps(self, character):
        return self.caps


class FakeFeatGrantRepository:
    """Records grant writes; serves configured existing grants."""

    def __init__(self, by_id=None, by_feat=None):
        self._by_id = by_id or {}
        self._by_feat = by_feat or {}
        self.add_calls = []
        self.set_calls = []
        self.remove_calls = []

    async def get_character_feat_by_feat_id(self, character_id, feat_id):
        return self._by_feat.get(feat_id)

    async def get_character_feat_by_id(self, character_id, character_feat_id):
        return self._by_id.get(character_feat_id)

    async def add_character_feat(
        self, character, feat_id, ability_score_increase_id, *, source_type=GrantSource.GM, commit=True
    ):
        self.add_calls.append((character, feat_id, ability_score_increase_id, source_type, commit))
        return make_grant(7, feat_id, ability_score_increase_id)

    async def set_character_feat_ability_score_increase(
        self, character, grant, ability_score_increase_id, *, commit=True
    ):
        self.set_calls.append((grant, ability_score_increase_id))
        self.set_commits = [*getattr(self, "set_commits", []), commit]
        grant.choices = [make_choice(ability_score_increase_id)] if ability_score_increase_id is not None else []
        return grant

    async def remove_character_feat(self, grant, *, commit=True):
        self.remove_calls.append(grant)
        self.remove_commits = [*getattr(self, "remove_commits", []), commit]
        return True


class FakeASIChoiceRepository:
    """Records audit rows written into character_asi_choices."""

    def __init__(self):
        self.add_calls = []

    async def add(
        self,
        character_id,
        class_level,
        choice_type,
        *,
        feat_id=None,
        ability_score_increase_id=None,
        increases=None,
        commit=True,
    ):
        self.add_calls.append(
            {
                "character_id": character_id,
                "class_level": class_level,
                "choice_type": choice_type,
                "feat_id": feat_id,
                "ability_score_increase_id": ability_score_increase_id,
                "commit": commit,
            }
        )
        return SimpleNamespace(id=1)


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    invalidate = AsyncMock()
    monkeypatch.setattr("app.features.characters.gm_panel.feats.service.invalidate_character_cache", invalidate)
    return invalidate


@pytest.fixture(autouse=True)
def no_feature_sync(monkeypatch):
    sync = AsyncMock()
    monkeypatch.setattr("app.features.characters.gm_panel.feats.service.sync_progression_features", sync)
    return sync


def make_service(character, *, feat=None, grants_by_id=None, grants_by_feat=None, stats=None):
    db = FakeAsyncSession()
    service = GmPanelFeatService(db)
    service.get_character_for_user = AsyncMock(return_value=character)
    service.feat_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=feat))
    service.feat_grant_repository = FakeFeatGrantRepository(by_id=grants_by_id, by_feat=grants_by_feat)
    service.asi_repository = FakeASIChoiceRepository()
    service.stats_service = stats or FakeStatsService()
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddFeat:
    async def test_adds_grant_with_audit_row_and_resync(self, no_feature_sync, no_cache_invalidate):
        character = make_character()
        service = make_service(character, feat=make_feat())

        result = await service.add_feat(character.id, CharacterFeatAdd(feat_id=2), SimpleNamespace())

        assert result.id == 7
        assert service.feat_grant_repository.add_calls == [(character, 2, None, GrantSource.GM, False)]
        assert len(service.asi_repository.add_calls) == 1
        audit = service.asi_repository.add_calls[0]
        assert audit["character_id"] == 1
        assert audit["class_level"] is None
        assert audit["choice_type"] == ASILevelChoice.FEAT
        assert audit["feat_id"] == 2
        assert audit["commit"] is False
        assert service.stats_service.refresh_calls == [character]
        service.get_character_for_user.assert_awaited_once()
        no_feature_sync.assert_awaited_once_with(service.repository.db, character)
        no_cache_invalidate.assert_awaited_once_with(character.id, db=service.repository.db)
        assert service.stats_service.refresh_commits == [False]
        assert service.repository.db.commits == 1

    async def test_add_feat_with_choice_writes_audit_and_refreshes_stats(self):
        character = make_character()
        stats = FakeStatsService()
        service = make_service(character, feat=make_feat(ability_effects=[(AbilityScore.STR, 1)]), stats=stats)

        await service.add_feat(
            character.id, CharacterFeatAdd(feat_id=2, ability_score_increase_id=200), SimpleNamespace()
        )

        assert service.feat_grant_repository.add_calls == [(character, 2, 200, GrantSource.GM, False)]
        assert service.asi_repository.add_calls[0]["ability_score_increase_id"] == 200
        assert stats.refresh_calls == [character]

    async def test_asi_offering_feat_can_be_granted_without_a_choice(self):
        """Unlike `update_feat`, a GM grant leaves the ASI choice group pending rather than requiring it up front."""

        character = make_character()
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1)])
        service = make_service(character, feat=feat)

        result = await service.add_feat(character.id, CharacterFeatAdd(feat_id=2), SimpleNamespace())

        assert result.id == 7
        assert service.feat_grant_repository.add_calls == [(character, 2, None, GrantSource.GM, False)]
        assert service.asi_repository.add_calls[0]["ability_score_increase_id"] is None

    async def test_cap_exceeded_does_not_reject_the_choice(self):
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1)])
        stats = FakeStatsService(totals={**TOTALS, "strength_total": 20})
        service = make_service(make_character(), feat=feat, stats=stats)

        result = await service.add_feat(
            1, CharacterFeatAdd(feat_id=2, ability_score_increase_id=200), SimpleNamespace()
        )

        assert result.id == 7
        add_call = service.feat_grant_repository.add_calls[0]
        assert add_call[0].id == 1  # the resolved Character object
        assert add_call[1:] == (2, 200, GrantSource.GM, False)

    async def test_prerequisite_not_met_rejects_the_grant(self):
        feat = make_feat(prerequisite_ability=AbilityScore.STR, prerequisite_minimum_score=15)
        service = make_service(make_character(), feat=feat)

        with pytest.raises(FeatPrerequisiteNotMetException):
            await service.add_feat(1, CharacterFeatAdd(feat_id=2), SimpleNamespace())

        assert service.feat_grant_repository.add_calls == []

    async def test_unknown_feat_raises(self):
        service = make_service(make_character(), feat=None)

        with pytest.raises(FeatNotFoundException):
            await service.add_feat(1, CharacterFeatAdd(feat_id=99), SimpleNamespace())

    async def test_duplicate_grant_raises(self):
        existing = make_grant(3, 2)
        service = make_service(make_character(), feat=make_feat(), grants_by_feat={2: existing})

        with pytest.raises(CharacterFeatAlreadyKnownException):
            await service.add_feat(1, CharacterFeatAdd(feat_id=2), SimpleNamespace())


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateFeat:
    async def test_updates_choice_and_refreshes_cache(self):
        character = make_character()
        grant = make_grant(3, 2, 200)
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1), (AbilityScore.DEX, 1)])
        service = make_service(character, feat=feat, grants_by_id={3: grant})

        result = await service.update_feat(1, 3, CharacterFeatUpdate(ability_score_increase_id=201), SimpleNamespace())

        assert result.choices[0].ability_effects[0].id == 201
        assert service.feat_grant_repository.set_calls == [(grant, 201)]
        assert service.feat_grant_repository.set_commits == [False]
        assert service.stats_service.refresh_calls == [character]
        assert service.stats_service.refresh_commits == [False]
        assert service.repository.db.commits == 1

    async def test_clearing_choice_on_asi_offering_feat_is_rejected(self):
        feat = make_feat(ability_effects=[(AbilityScore.STR, 1)])
        grant = make_grant(3, 2, 200)
        service = make_service(make_character(), feat=feat, grants_by_id={3: grant})

        with pytest.raises(FeatAsiChoiceRequiredException):
            await service.update_feat(1, 3, CharacterFeatUpdate(ability_score_increase_id=None), SimpleNamespace())

        assert service.feat_grant_repository.set_calls == []

    async def test_missing_grant_raises(self):
        service = make_service(make_character())

        with pytest.raises(CharacterFeatNotFoundException):
            await service.update_feat(1, 42, CharacterFeatUpdate(ability_score_increase_id=10), SimpleNamespace())


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveFeat:
    async def test_removes_grant_syncs_features_and_refreshes_cache(self):
        character = make_character()
        grant = make_grant(3, 2)
        service = make_service(character, grants_by_id={3: grant})

        result = await service.remove_feat(1, 3, SimpleNamespace())

        assert result is True
        assert service.feat_grant_repository.remove_calls == [grant]
        assert service.feat_grant_repository.remove_commits == [False]
        assert service.repository.db.commits == 1
        assert service.stats_service.refresh_calls == [character]
        assert service.stats_service.refresh_commits == [False]

    async def test_missing_grant_raises(self):
        service = make_service(make_character())

        with pytest.raises(CharacterFeatNotFoundException):
            await service.remove_feat(1, 42, SimpleNamespace())


@pytest.mark.unit
@pytest.mark.asyncio
class TestRefreshFailureIsAtomic:
    """The ability-score refresh shares the grant's transaction: a failing refresh leaves nothing behind."""

    @pytest.fixture
    def real_purge(self, monkeypatch, no_cache_invalidate):
        from app.features.characters.cache import invalidate_character_cache

        purge = AsyncMock()
        monkeypatch.setattr("app.features.characters.cache.cache_delete_key", purge)
        monkeypatch.setattr(
            "app.features.characters.gm_panel.feats.service.invalidate_character_cache", invalidate_character_cache
        )
        return purge

    async def test_add_feat_rolls_back_and_purges_nothing(self, real_purge):
        stats = FakeStatsService()
        stats.refresh_error = RuntimeError("refresh failed")
        service = make_service(make_character(), feat=make_feat(), stats=stats)

        with pytest.raises(RuntimeError):
            await service.add_feat(1, CharacterFeatAdd(feat_id=2), SimpleNamespace())

        assert (service.repository.db.commits, service.repository.db.rollbacks) == (0, 1)
        real_purge.assert_not_awaited()

    async def test_remove_feat_rolls_back_and_purges_nothing(self, real_purge):
        stats = FakeStatsService()
        stats.refresh_error = RuntimeError("refresh failed")
        service = make_service(make_character(), grants_by_id={3: make_grant(3, 2)}, stats=stats)

        with pytest.raises(RuntimeError):
            await service.remove_feat(1, 3, SimpleNamespace())

        assert (service.repository.db.commits, service.repository.db.rollbacks) == (0, 1)
        real_purge.assert_not_awaited()

    async def test_purge_runs_only_after_the_commit(self, real_purge):
        service = make_service(make_character(), grants_by_id={3: make_grant(3, 2)})
        order = []

        async def record(key):
            order.append(("purge", service.repository.db.commits))

        real_purge.side_effect = record

        await service.remove_feat(1, 3, SimpleNamespace())

        assert order == [("purge", 1)]
