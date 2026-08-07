"""Unit tests for CharacterStatsService with a fake stats repository."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import ArmorSpec, DerivedStats
from app.features.characters.ability_score.service import CharacterStatsService
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
    """Stands in for CharacterStatsRepository, recording calls."""

    def __init__(self, cache_row=None, race_bonuses=None, feat_increases=None, classes=None, races=None, armor=None):
        self.cache_row = cache_row
        self.race_bonuses = race_bonuses or []
        self.feat_increases = feat_increases or []
        self.classes = classes or {}
        self.races = races or {}
        self.armor = armor or {}
        self.get_by_calls = []
        self.get_many_calls = []
        self.get_race_bonus_calls = []
        self.get_feat_increase_calls = []
        self.upsert_calls = []
        self.get_classes_calls = []
        self.get_races_calls = []
        self.get_armor_calls = []

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

    def get_classes(self, class_ids):
        self.get_classes_calls.append(class_ids)
        return {cid: self.classes[cid] for cid in class_ids if cid in self.classes}

    def get_races(self, race_ids):
        self.get_races_calls.append(race_ids)
        return {rid: self.races[rid] for rid in race_ids if rid in self.races}

    def get_armor_by_character_ids(self, character_ids):
        self.get_armor_calls.append(character_ids)
        return {cid: self.armor[cid] for cid in character_ids if cid in self.armor}


def make_service(**fake_kwargs) -> tuple[CharacterStatsService, FakeCacheRepository]:
    fake = FakeCacheRepository(**fake_kwargs)
    service = CharacterStatsService(db=None)
    service.repository = fake
    return service, fake


@pytest.mark.unit
class TestCharacterStatsService:
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

    def test_get_many_derived_assembles_stats_from_references(self):
        character = make_character(id=7, dexterity=14)
        fighter = SimpleNamespace(hit_dice=SimpleNamespace(value="D10"))
        elf = SimpleNamespace(speed=25)
        armor = [ArmorSpec(base=11, dex_bonus=True, max_dex_bonus=None)]
        service, fake = make_service(classes={1: fighter}, races={5: elf}, armor={7: armor})

        result = service.get_many_derived([character], {7: None})

        assert fake.get_classes_calls == [[1]]
        assert fake.get_races_calls == [[5]]
        assert fake.get_armor_calls == [[7]]
        assert result == {7: DerivedStats(hit_dice="D10", speed=25, armor_class=13)}

    def test_get_many_derived_uses_dex_total_from_cache(self):
        character = make_character(id=7, dexterity=14)
        service, fake = make_service(classes={1: SimpleNamespace(hit_dice=SimpleNamespace(value="D8"))})

        result = service.get_many_derived([character], {7: 18})

        assert result[7].armor_class == 14

    def test_get_many_derived_falls_back_to_defaults_without_references(self):
        character = make_character(id=7, class_id=None, race_id=None, dexterity=10)
        service, fake = make_service()

        result = service.get_many_derived([character], {7: None})

        assert fake.get_classes_calls == [[]]
        assert fake.get_races_calls == [[]]
        assert result == {7: DerivedStats(hit_dice="", speed=30, armor_class=10)}
