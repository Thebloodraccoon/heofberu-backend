"""Unit tests for CharacterAbilityCacheService with a fake cache repository."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.service import CharacterAbilityCacheService
from app.models.character_model import Character
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus


def make_character(**overrides) -> Character:
    base = {
        "id": 1,
        "owner_id": 1,
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 8,
        "wisdom": 9,
        "charisma": 11,
    }
    base.update(overrides)
    return Character(**base)


class FakeCacheRepository:
    """Stands in for CharacterAbilityScoreCacheRepository, recording calls."""

    def __init__(self, cache_row=None, race_bonuses=None, feat_increases=None):
        self.cache_row = cache_row
        self.race_bonuses = race_bonuses or []
        self.feat_increases = feat_increases or []
        self.get_by_calls = []
        self.get_many_calls = []
        self.get_race_bonus_calls = []
        self.get_feat_increase_calls = []
        self.upsert_calls = []

    def get_by_character_id(self, character_id):
        self.get_by_calls.append(character_id)
        return self.cache_row

    def get_many_by_character_ids(self, character_ids):
        self.get_many_calls.append(character_ids)
        return dict.fromkeys(character_ids, self.cache_row)

    def get_race_bonuses(self, race_id):
        self.get_race_bonus_calls.append(race_id)
        return self.race_bonuses

    def get_feat_increases(self, character_id):
        self.get_feat_increase_calls.append(character_id)
        return self.feat_increases

    def upsert(self, character_id, totals):
        self.upsert_calls.append((character_id, totals))
        return self.cache_row


def make_service(**fake_kwargs) -> tuple[CharacterAbilityCacheService, FakeCacheRepository]:
    fake = FakeCacheRepository(**fake_kwargs)
    service = CharacterAbilityCacheService(db=None)
    service.cache_repository = fake
    return service, fake


@pytest.mark.unit
class TestCharacterAbilityCacheService:
    def test_compute_loads_bonus_rows_and_returns_totals_without_persisting(self):
        fake_kwargs = {
            "race_bonuses": [RaceAbilityBonus(race_id=5, ability=AbilityScore.DEX, bonus=2)],
            "feat_increases": [FeatAbilityScoreIncrease(feat_id=1, ability=AbilityScore.STR, amount=1)],
        }
        service, fake = make_service(**fake_kwargs)

        totals = service.compute(make_character())

        assert totals["strength_total"] == 15
        assert totals["dexterity_total"] == 12
        assert fake.get_race_bonus_calls == [5]
        assert fake.get_feat_increase_calls == [1]
        assert fake.upsert_calls == []

    def test_compute_without_race_queries_race_bonuses_as_none(self):
        service, fake = make_service()

        service.compute(make_character(race_id=None))

        assert fake.get_race_bonus_calls == [None]

    def test_get_or_stale_returns_cached_row_without_recomputing(self):
        row = SimpleNamespace(strength_total=99)
        service, fake = make_service(cache_row=row)

        result = service.get_or_stale(1)

        assert result is row
        assert fake.get_by_calls == [1]
        assert fake.get_race_bonus_calls == []
        assert fake.get_feat_increase_calls == []

    def test_get_many_or_stale_delegates_to_repository(self):
        row = SimpleNamespace(strength_total=99)
        service, fake = make_service(cache_row=row)

        result = service.get_many_or_stale([1, 2])

        assert fake.get_many_calls == [[1, 2]]
        assert result == {1: row, 2: row}

    def test_for_response_without_refresh_reads_existing_row(self):
        row = SimpleNamespace(strength_total=99)
        service, fake = make_service(cache_row=row)

        result = service.for_response(make_character(), refresh=False)

        assert result is row
        assert fake.get_by_calls == [1]
        assert fake.upsert_calls == []

    def test_for_response_with_refresh_recomputes_and_persists(self):
        row = SimpleNamespace(strength_total=14)
        service, fake = make_service(cache_row=row)

        result = service.for_response(make_character(), refresh=True)

        assert result is row
        assert fake.upsert_calls == [
            (
                1,
                {
                    "strength_total": 14,
                    "dexterity_total": 10,
                    "constitution_total": 12,
                    "intelligence_total": 8,
                    "wisdom_total": 9,
                    "charisma_total": 11,
                },
            )
        ]
