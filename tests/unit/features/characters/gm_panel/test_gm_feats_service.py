"""Unit tests for GmPanelFeatService: grant/update/revoke feat grants on a character."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, ASILevelChoice
from app.features.characters.gm_panel.exceptions import (
    CharacterFeatAlreadyKnownException,
    CharacterFeatNotFoundException,
    FeatAsiChoiceRequiredException,
    FeatPrerequisiteNotMetException,
)
from app.features.characters.gm_panel.feats.schemas import CharacterFeatAdd, CharacterFeatUpdate
from app.features.characters.gm_panel.feats.service import GmPanelFeatService
from app.features.characters.progression.exceptions import AbilityScoreCapExceededException
from app.features.feats.exceptions import FeatNotFoundException
from app.models.character_model import Character
from tests.unit.fakes import FakeAsyncSession


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


def make_feat(**overrides) -> SimpleNamespace:
    base = {
        "id": 2,
        "name": "Tough",
        "description": "More hit points.",
        "ability_score_increases": [],
        "prerequisite_ability": None,
        "prerequisite_minimum_score": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_increase(increase_id: int, ability: AbilityScore, amount: int) -> SimpleNamespace:
    return SimpleNamespace(id=increase_id, feat_id=2, ability=ability, amount=amount)


def make_grant(grant_id: int, feat_id: int, ability_score_increase_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=grant_id,
        character_id=1,
        feat_id=feat_id,
        ability_score_increase_id=ability_score_increase_id,
        source_type="GM",
        feat=SimpleNamespace(id=feat_id, name="Tough", description=""),
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

    async def refresh(self, character):
        self.refresh_calls.append(character)

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

    async def add_character_feat(self, character_id, feat_id, ability_score_increase_id, *, commit=True):
        self.add_calls.append((character_id, feat_id, ability_score_increase_id, commit))
        return make_grant(7, feat_id, ability_score_increase_id)

    async def set_character_feat_ability_score_increase(self, grant, ability_score_increase_id):
        self.set_calls.append((grant, ability_score_increase_id))
        grant.ability_score_increase_id = ability_score_increase_id
        return grant

    async def remove_character_feat(self, grant):
        self.remove_calls.append(grant)
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
        assert result.feat_id == 2
        assert service.feat_grant_repository.add_calls == [(1, 2, None, False)]
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
        no_cache_invalidate.assert_awaited_once_with(character.id)

    async def test_add_feat_with_choice_writes_audit_and_refreshes_stats(self):
        character = make_character()
        increase = make_increase(10, AbilityScore.STR, 1)
        stats = FakeStatsService()
        service = make_service(character, feat=make_feat(ability_score_increases=[increase]), stats=stats)

        await service.add_feat(character.id, CharacterFeatAdd(feat_id=2, ability_score_increase_id=10), SimpleNamespace())

        assert service.feat_grant_repository.add_calls == [(1, 2, 10, False)]
        assert service.asi_repository.add_calls[0]["ability_score_increase_id"] == 10
        assert stats.refresh_calls == [character]

    async def test_asi_offering_feat_requires_explicit_choice(self):
        feat = make_feat(ability_score_increases=[make_increase(10, AbilityScore.STR, 1)])
        service = make_service(make_character(), feat=feat)

        with pytest.raises(FeatAsiChoiceRequiredException) as exc_info:
            await service.add_feat(1, CharacterFeatAdd(feat_id=2), SimpleNamespace())

        assert exc_info.value.status_code == 422
        assert service.feat_grant_repository.add_calls == []
        assert service.asi_repository.add_calls == []

    async def test_cap_exceeded_rejects_the_choice(self):
        increase = make_increase(10, AbilityScore.STR, 1)
        feat = make_feat(ability_score_increases=[increase])
        stats = FakeStatsService(totals={**TOTALS, "strength_total": 20})
        service = make_service(make_character(), feat=feat, stats=stats)

        with pytest.raises(AbilityScoreCapExceededException):
            await service.add_feat(1, CharacterFeatAdd(feat_id=2, ability_score_increase_id=10), SimpleNamespace())

        assert service.feat_grant_repository.add_calls == []

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
        grant = make_grant(3, 2, 10)
        feat = make_feat(ability_score_increases=[make_increase(10, AbilityScore.STR, 1), make_increase(11, AbilityScore.DEX, 1)])
        service = make_service(character, feat=feat, grants_by_id={3: grant})

        result = await service.update_feat(1, 3, CharacterFeatUpdate(ability_score_increase_id=11), SimpleNamespace())

        assert result.ability_score_increase_id == 11
        assert service.feat_grant_repository.set_calls == [(grant, 11)]
        assert service.stats_service.refresh_calls == [character]

    async def test_clearing_choice_on_asi_offering_feat_is_rejected(self):
        feat = make_feat(ability_score_increases=[make_increase(10, AbilityScore.STR, 1)])
        grant = make_grant(3, 2, 10)
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
        assert service.repository.db.commits == 1
        assert service.stats_service.refresh_calls == [character]

    async def test_missing_grant_raises(self):
        service = make_service(make_character())

        with pytest.raises(CharacterFeatNotFoundException):
            await service.remove_feat(1, 42, SimpleNamespace())
