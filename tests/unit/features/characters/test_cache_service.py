"""Unit tests for CharacterStatsService with a fake stats repository."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import DerivedStats
from app.features.characters.ability_score.service import CharacterStatsService
from app.models.character.character_model import Character
from app.models.races.race_association_models import RaceAbilityBonus
from app.models.races.subrace_association_models import SubraceAbilityBonus


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

    def __init__(
        self,
        cache_row=None,
        race_bonuses=None,
        subrace_bonuses=None,
        asi_increases=None,
        feature_increases=None,
        hit_dice=None,
        race_names=None,
        subrace_names=None,
    ):
        self.cache_row = cache_row
        self.race_bonuses = race_bonuses or []
        self.subrace_bonuses = subrace_bonuses or []
        self.asi_increases = asi_increases or []
        self.feature_increases = feature_increases or []
        self.hit_dice = hit_dice or {}
        self.race_names = race_names or {}
        self.subrace_names = subrace_names or {}
        self.get_by_calls = []
        self.get_many_calls = []
        self.upsert_calls = []
        self.get_hit_dice_calls = []
        self.get_race_bonuses_many_calls = []
        self.get_subrace_bonuses_many_calls = []
        self.get_asi_increases_many_calls = []
        self.get_feature_increases_many_calls = []
        self.upsert_many_calls = []

    async def get_by_character_id(self, character_id):
        self.get_by_calls.append(character_id)
        return self.cache_row

    async def get_many_by_character_ids(self, character_ids):
        self.get_many_calls.append(character_ids)
        return dict.fromkeys(character_ids, self.cache_row)

    async def upsert(self, character_id, totals, *, commit=True):
        self.upsert_calls.append((character_id, totals, commit))
        return self.cache_row

    async def get_hit_dice(self, class_ids):
        self.get_hit_dice_calls.append(list(class_ids))
        return {cid: self.hit_dice[cid] for cid in class_ids if cid in self.hit_dice}

    async def get_race_names(self, race_ids):
        return {rid: self.race_names[rid] for rid in race_ids if rid in self.race_names}

    async def get_subrace_names(self, subrace_ids):
        return {sid: self.subrace_names[sid] for sid in subrace_ids if sid in self.subrace_names}

    async def get_race_bonuses_many(self, race_ids):
        self.get_race_bonuses_many_calls.append(list(race_ids))
        return {race_id: self.race_bonuses for race_id in race_ids if race_id is not None}

    async def get_subrace_bonuses_many(self, subrace_ids):
        self.get_subrace_bonuses_many_calls.append(list(subrace_ids))
        return {subrace_id: self.subrace_bonuses for subrace_id in subrace_ids if subrace_id is not None}

    async def get_asi_increases_many(self, character_ids):
        self.get_asi_increases_many_calls.append(list(character_ids))
        return dict.fromkeys(character_ids, self.asi_increases)

    async def get_feature_increases_many(self, character_ids):
        self.get_feature_increases_many_calls.append(list(character_ids))
        return dict.fromkeys(character_ids, self.feature_increases)

    async def upsert_many(self, totals_by_character_id, *, commit=True):
        self.upsert_many_calls.append((dict(totals_by_character_id), commit))
        return dict.fromkeys(totals_by_character_id, self.cache_row)


def make_service(**fake_kwargs) -> tuple[CharacterStatsService, FakeCacheRepository]:
    fake = FakeCacheRepository(**fake_kwargs)
    service = CharacterStatsService(db=None)
    service.repository = fake
    return service, fake


@pytest.mark.unit
@pytest.mark.asyncio
class TestCharacterStatsService:
    async def test_compute_loads_bonus_rows_and_returns_totals_without_persisting(self):
        fake_kwargs = {
            "race_bonuses": [RaceAbilityBonus(race_id=5, ability=AbilityScore.DEX, bonus=2)],
            "subrace_bonuses": [SubraceAbilityBonus(subrace_id=7, ability=AbilityScore.INT, bonus=1)],
        }
        service, fake = make_service(**fake_kwargs)

        totals = await service.compute(make_character(subrace_id=7))

        assert totals["strength_total"] == 14
        assert totals["dexterity_total"] == 12
        assert totals["intelligence_total"] == 9
        assert fake.get_race_bonuses_many_calls == [[5]]
        assert fake.get_subrace_bonuses_many_calls == [[7]]
        assert fake.get_asi_increases_many_calls == [[1]]
        assert fake.get_feature_increases_many_calls == [[1]]
        assert fake.upsert_calls == []

    async def test_compute_counts_asi_log_increases(self):
        service, fake = make_service(asi_increases=[SimpleNamespace(ability=AbilityScore.STR, amount=2)])

        totals = await service.compute(make_character())

        assert totals["strength_total"] == 16
        assert fake.get_asi_increases_many_calls == [[1]]

    async def test_compute_counts_feature_effects_and_floors_at_one(self):
        service, _ = make_service(
            feature_increases=[
                SimpleNamespace(ability=AbilityScore.STR, amount=4, new_cap=None),
                SimpleNamespace(ability=AbilityScore.INT, amount=-20, new_cap=None),
            ]
        )

        totals = await service.compute(make_character())

        assert totals["strength_total"] == 18
        assert totals["intelligence_total"] == 1

    async def test_compute_without_race_passes_no_race_to_the_bonus_lookups(self):
        service, fake = make_service()

        await service.compute(make_character(race_id=None))

        assert fake.get_race_bonuses_many_calls == [[None]]
        assert fake.get_subrace_bonuses_many_calls == [[None]]

    async def test_get_or_stale_returns_cached_row_without_recomputing(self):
        row = SimpleNamespace(strength_total=99)
        service, fake = make_service(cache_row=row)

        result = await service.get_or_stale(1)

        assert result is row
        assert fake.get_by_calls == [1]
        assert fake.get_race_bonuses_many_calls == []

    async def test_get_many_or_stale_delegates_to_repository(self):
        row = SimpleNamespace(strength_total=99)
        service, fake = make_service(cache_row=row)

        result = await service.get_many_or_stale([1, 2])

        assert fake.get_many_calls == [[1, 2]]
        assert result == {1: row, 2: row}

    async def test_get_many_derived_reads_hit_dice_from_the_class(self):
        service, fake = make_service(hit_dice={1: "D10"})

        result = await service.get_many_derived([make_character(id=7)])

        assert fake.get_hit_dice_calls == [[1]]
        assert result == {7: DerivedStats(hit_dice="D10")}

    async def test_get_many_derived_is_empty_without_a_class(self):
        service, fake = make_service()

        result = await service.get_many_derived([make_character(id=7, class_id=None, race_id=None)])

        assert fake.get_hit_dice_calls == [[]]
        assert result == {7: DerivedStats(hit_dice="")}

    async def test_compute_derived_returns_the_single_characters_stats(self):
        service, _ = make_service(hit_dice={1: "D8"})

        assert await service.compute_derived(make_character(id=3)) == DerivedStats(hit_dice="D8")

    async def test_compute_breakdown_labels_every_source(self):
        service, _ = make_service(
            race_bonuses=[RaceAbilityBonus(race_id=5, ability=AbilityScore.DEX, bonus=2)],
            subrace_bonuses=[SubraceAbilityBonus(subrace_id=7, ability=AbilityScore.DEX, bonus=1)],
            asi_increases=[SimpleNamespace(ability=AbilityScore.DEX, amount=2, choice=None)],
            race_names={5: "Elf"},
            subrace_names={7: "High Elf"},
        )

        breakdown = await service.compute_breakdown(make_character(subrace_id=7))

        dexterity = breakdown[AbilityScore.DEX]
        assert dexterity.base == 10
        assert dexterity.total == 15
        assert [(c.source, c.label, c.amount) for c in dexterity.contributions] == [
            ("race", "Elf", 2),
            ("subrace", "High Elf", 1),
            ("asi", "GM adjustment", 2),
        ]
        assert breakdown[AbilityScore.STR].contributions == []

    async def test_compute_many_batches_bonus_lookups_across_characters(self):
        fake_kwargs = {
            "race_bonuses": [RaceAbilityBonus(race_id=5, ability=AbilityScore.DEX, bonus=2)],
            "subrace_bonuses": [SubraceAbilityBonus(subrace_id=7, ability=AbilityScore.INT, bonus=1)],
        }
        service, fake = make_service(**fake_kwargs)
        character_a = make_character(id=1, subrace_id=7)
        character_b = make_character(id=2, race_id=5, subrace_id=None)

        totals_by_character = await service.compute_many([character_a, character_b])

        assert set(totals_by_character) == {1, 2}
        assert totals_by_character[1]["dexterity_total"] == 12
        assert totals_by_character[1]["intelligence_total"] == 9
        assert totals_by_character[2]["dexterity_total"] == 12
        assert fake.get_race_bonuses_many_calls == [[5, 5]]
        assert fake.get_subrace_bonuses_many_calls == [[7, None]]
        assert fake.get_asi_increases_many_calls == [[1, 2]]
        assert fake.get_feature_increases_many_calls == [[1, 2]]

    async def test_compute_many_empty_list_returns_empty(self):
        service, fake = make_service()

        result = await service.compute_many([])

        assert result == {}
        assert fake.get_race_bonuses_many_calls == [[]]

    async def test_refresh_many_persists_batched_totals(self):
        service, fake = make_service()

        result = await service.refresh_many([make_character(id=1), make_character(id=2, race_id=None)], commit=False)

        assert set(result) == {1, 2}
        totals_by_character, commit = fake.upsert_many_calls[0]
        assert set(totals_by_character) == {1, 2}
        assert commit is False

    async def test_refresh_many_with_empty_list_skips_repository(self):
        service, fake = make_service()

        result = await service.refresh_many([])

        assert result == {}
        assert fake.upsert_many_calls == []
