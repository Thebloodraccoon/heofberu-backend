"""Unit tests for CharacterProgressionService with fake repositories and a fake stats service."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import ABILITY_SCORE_CAP, ASI_LEVELS, AbilityScore, ASILevelChoice, CharacterFeatSource, UserRole
from app.features.characters.crud.exceptions import SkillNotAvailableForClassException, TooManySkillChoicesException
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.feats.exceptions import (
    CharacterFeatAlreadyKnownException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.characters.progression.exceptions import (
    AbilityScoreCapExceededException,
    BackgroundAlreadySetException,
    CharacterAlreadyAtMaxLevelException,
    InvalidHitPointGainException,
    InvalidRebuildMaxHpException,
    LevelUpChoiceNotAllowedException,
    LevelUpChoiceRequiredException,
    RebuildAsiChoicesMismatchException,
)
from app.features.characters.progression.schemas import (
    ASIChoice,
    ASIIncreaseItem,
    BackgroundChange,
    CanLevelUpResponse,
    CharacterRebuildRequest,
    FeatChoice,
    LevelUpRequest,
    SubclassChange,
    SubraceChange,
)
from app.features.characters.progression.service import CharacterProgressionService
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.feats.exceptions import FeatNotFoundException
from app.features.races.exceptions import RaceNotFoundException, SubraceNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_association_models import CharacterSkillProficiency
from app.models.character_model import Character
from tests.unit.fakes import FakeAsyncSession, FakeResult


def make_character(**overrides) -> Character:
    base = {
        "id": 1,
        "owner_id": 1,
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "level": 3,
        "max_hp": 20,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 8,
        "wisdom": 9,
        "charisma": 11,
    }
    base.update(overrides)
    return Character(**base)


def make_user() -> UserResponse:
    return UserResponse(
        id=1,
        username="gm_user",
        email="gm@example.com",
        role=UserRole.GM,
        created_at=datetime.now(timezone.utc),
    )


def default_totals() -> dict[str, int]:
    return {
        "strength_total": 14,
        "dexterity_total": 10,
        "constitution_total": 14,
        "intelligence_total": 8,
        "wisdom_total": 9,
        "charisma_total": 11,
    }


class FakeStatsService:
    """Stands in for CharacterStatsService inside the progression service."""

    def __init__(self, totals=None, caps=None):
        self.totals = totals or default_totals()
        self.caps = caps or dict.fromkeys(AbilityScore, ABILITY_SCORE_CAP)
        self.compute_calls = []
        self.resolve_caps_calls = []
        self.refresh_calls = []

    async def compute(self, character):
        self.compute_calls.append(character)
        return dict(self.totals)

    async def resolve_ability_caps(self, character):
        self.resolve_caps_calls.append(character)
        return dict(self.caps)

    async def refresh(self, character):
        self.refresh_calls.append(character)


class FakeCharacterRepository:
    def __init__(self, db, character):
        self.db = db
        self.character = character
        self.light_calls = []

    async def get_by_id_light(self, character_id):
        self.light_calls.append(character_id)
        return self.character


class FakeCharacterService:
    def __init__(self):
        self.reapply_calls = []

    async def reapply_spell_slot_progression(self, character, *, commit=True):
        self.reapply_calls.append((character.id, commit))


class FakeClassRepository:
    def __init__(self, class_row=None, subclass_row=None):
        self.class_row = class_row
        self.subclass_row = subclass_row

    async def get_by_id(self, class_id):
        return self.class_row

    async def get_subclass(self, class_id, subclass_id):
        return self.subclass_row


class FakeRaceRepository:
    def __init__(self, race=None, subrace_row=None, exists=True):
        self.race = race
        self.subrace_row = subrace_row
        self.exists = exists

    async def get_subrace(self, race_id, subrace_id):
        return self.subrace_row

    async def get_by_id(self, race_id):
        return self.race

    async def exists_by_id(self, race_id):
        return self.exists


class FakeBackgroundRepository:
    def __init__(self, background=None, exists=None):
        self.background = background
        self.exists = (background is not None) if exists is None else exists

    async def get_by_id(self, background_id):
        return self.background

    async def exists_by_id(self, background_id):
        return self.exists


class FakeCharacterSpellRepository:
    def __init__(self):
        self.clear_calls = []

    async def clear_known_spells(self, character_id, *, commit=True):
        self.clear_calls.append((character_id, commit))


class FakeItemRepository:
    def __init__(self, entries=None, choice_groups=None):
        self.entries = entries or []
        self.choice_groups = choice_groups or []

    async def get_source_items_for_sources(self, sources):
        return list(self.entries)

    async def get_choice_groups_for_sources(self, sources):
        return list(self.choice_groups)


class FakeFeatRepository:
    def __init__(self, feat=None):
        self.feat = feat

    async def get_by_id(self, feat_id):
        return self.feat if self.feat is not None and self.feat.id == feat_id else None


class FakeFeatGrantRepository:
    def __init__(self, known_feat_ids=()):
        self.known_feat_ids = set(known_feat_ids)
        self.add_calls = []
        self.remove_by_source_calls = []

    async def get_character_feat_by_feat_id(self, character_id, feat_id):
        return SimpleNamespace() if feat_id in self.known_feat_ids else None

    async def add_character_feat(
        self, character_id, feat_id, ability_score_increase_id=None, *, source_type=None, commit=True
    ):
        self.add_calls.append((character_id, feat_id, ability_score_increase_id, source_type, commit))

    async def remove_feats_by_source(self, character_id, source_type, *, commit=True):
        self.remove_by_source_calls.append((character_id, source_type, commit))


class FakeASIRepository:
    def __init__(self, choices=None):
        self.choices = choices or []
        self.add_calls = []
        self.clear_calls = []

    async def get_character_choices(self, character_id):
        return list(self.choices)

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
            (character_id, class_level, choice_type, feat_id, ability_score_increase_id, increases, commit)
        )
        return SimpleNamespace(id=len(self.add_calls))

    async def clear_character_choices(self, character_id, *, commit=True):
        self.clear_calls.append((character_id, commit))


class FakeMaxLevelRepository:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    async def get_by_character_id(self, character_id):
        self.calls.append(character_id)
        return self.row


def make_service(
    character=None,
    *,
    max_level_row=None,
    class_row=None,
    subclass_row=None,
    race=None,
    subrace_row=None,
    race_exists=True,
    background=None,
    background_exists=None,
    feat=None,
    known_feat_ids=(),
    asi_choices=None,
    item_entries=None,
    totals=None,
    caps=None,
):
    character = character or make_character()
    db = FakeAsyncSession()
    service = CharacterProgressionService(db)
    service.repository = FakeCharacterRepository(db, character)
    service.character_service = FakeCharacterService()
    service.class_repository = FakeClassRepository(class_row=class_row, subclass_row=subclass_row)
    service.race_repository = FakeRaceRepository(race=race, subrace_row=subrace_row, exists=race_exists)
    service.background_repository = FakeBackgroundRepository(background=background, exists=background_exists)
    service.item_repository = FakeItemRepository(entries=item_entries)
    service.feat_repository = FakeFeatRepository(feat=feat)
    service.feat_grant_repository = FakeFeatGrantRepository(known_feat_ids=known_feat_ids)
    service.asi_repository = FakeASIRepository(choices=asi_choices)
    service.max_level_repository = FakeMaxLevelRepository(row=max_level_row)
    service.stats_service = FakeStatsService(totals=totals, caps=caps)
    service.character_spell_repository = FakeCharacterSpellRepository()
    return service, db


@pytest.fixture(autouse=True)
def no_feature_sync(monkeypatch):
    monkeypatch.setattr("app.features.characters.progression.service.sync_progression_features", AsyncMock())


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.progression.service.invalidate_character_cache", AsyncMock())


@pytest.mark.unit
@pytest.mark.asyncio
class TestCanLevelUp:
    async def test_reports_true_with_gm_set_max_above_current_level(self):
        service, _ = make_service(make_character(level=3), max_level_row=SimpleNamespace(max_level=5))

        response = await service.can_level_up(1, make_user())

        assert isinstance(response, CanLevelUpResponse)
        assert response.can_level_up is True
        assert response.current_level == 3
        assert response.max_level == 5

    async def test_missing_max_level_row_caps_at_current_level(self):
        service, _ = make_service(make_character(level=3), max_level_row=None)

        response = await service.can_level_up(1, make_user())

        assert response.can_level_up is False
        assert response.max_level == 3

    async def test_blocked_when_already_at_gm_cap(self):
        service, _ = make_service(make_character(level=5), max_level_row=SimpleNamespace(max_level=5))

        response = await service.can_level_up(1, make_user())

        assert response.can_level_up is False
        assert (response.current_level, response.max_level) == (5, 5)


@pytest.mark.unit
@pytest.mark.asyncio
class TestLevelUpGate:
    async def test_level_up_at_max_level_raises_and_never_commits(self):
        character = make_character(level=5)
        service, db = make_service(character, max_level_row=SimpleNamespace(max_level=5))

        with pytest.raises(CharacterAlreadyAtMaxLevelException):
            await service.level_up(1, LevelUpRequest(), make_user())

        assert character.level == 5
        assert db.commits == 0
        assert db.rollbacks == 0

    async def test_choice_required_at_asi_level(self):
        service, _ = make_service(make_character(level=3), max_level_row=SimpleNamespace(max_level=20))

        with pytest.raises(LevelUpChoiceRequiredException):
            await service.level_up(1, LevelUpRequest(), make_user())

    async def test_choice_rejected_on_non_asi_level(self):
        service, _ = make_service(make_character(level=5), max_level_row=SimpleNamespace(max_level=20))

        choice = ASIChoice(increases=[ASIIncreaseItem(ability=AbilityScore.STR, amount=2)])
        with pytest.raises(LevelUpChoiceNotAllowedException):
            await service.level_up(1, LevelUpRequest(choice=choice), make_user())

    async def test_missing_max_level_row_blocks_level_up_defensively(self):
        service, _ = make_service(make_character(level=3), max_level_row=None)

        with pytest.raises(CharacterAlreadyAtMaxLevelException):
            await service.level_up(1, LevelUpRequest(), make_user())

    async def test_asi_levels_are_the_documented_set(self):
        assert frozenset({4, 8, 12, 16, 19}) == ASI_LEVELS


@pytest.mark.unit
@pytest.mark.asyncio
class TestLevelUpHappyPath:
    def make_ready_service(self, level=2, hit_dice="D10"):
        return make_service(
            make_character(level=level),
            max_level_row=SimpleNamespace(max_level=20),
            class_row=SimpleNamespace(hit_dice=SimpleNamespace(value=hit_dice)),
        )

    async def test_default_hp_gain_is_half_die_plus_one_plus_con_modifier(self):
        service, db = self.make_ready_service()
        character = service.repository.character

        await service.level_up(1, LevelUpRequest(), make_user())

        assert character.level == 3
        assert character.max_hp == 28
        assert db.commits == 1
        assert service.stats_service.refresh_calls == [character]
        assert service.asi_repository.add_calls == []
        assert service.character_service.reapply_calls == [(1, False)]

    async def test_explicit_hit_points_gained_within_bounds_is_used(self):
        service, _ = self.make_ready_service()

        await service.level_up(1, LevelUpRequest(hit_points_gained=3), make_user())

        assert service.repository.character.max_hp == 23

    async def test_explicit_hit_points_gained_above_die_plus_con_raises(self):
        service, db = self.make_ready_service()

        with pytest.raises(InvalidHitPointGainException):
            await service.level_up(1, LevelUpRequest(hit_points_gained=13), make_user())

        assert db.commits == 0

    async def test_default_hp_gain_floors_at_one(self):
        service, _ = self.make_ready_service(hit_dice="D6")
        service.stats_service.totals["constitution_total"] = 1

        await service.level_up(1, LevelUpRequest(), make_user())

        assert service.repository.character.max_hp == 21

    async def test_level_up_restores_current_hp_to_new_max_and_clears_temp_hp(self):
        service, _ = make_service(
            make_character(level=2, max_hp=20, current_hp=8, temp_hp=5),
            max_level_row=SimpleNamespace(max_level=20),
            class_row=SimpleNamespace(hit_dice=SimpleNamespace(value="D10")),
        )
        character = service.repository.character

        await service.level_up(1, LevelUpRequest(), make_user())

        assert character.max_hp == 28
        assert character.current_hp == 28
        assert character.temp_hp == 0

    async def test_features_synced_and_spell_slots_reapplied_without_own_commit(self):
        service, db = self.make_ready_service()

        await service.level_up(1, LevelUpRequest(), make_user())

        assert db.commits == 1
        assert service.character_service.reapply_calls == [(1, False)]


@pytest.mark.unit
@pytest.mark.asyncio
class TestLevelUpAsi:
    def make_asi_service(self, totals=None, caps=None):
        return make_service(
            make_character(level=3),
            max_level_row=SimpleNamespace(max_level=20),
            totals=totals,
            caps=caps,
        )

    async def test_valid_increase_records_audit_row_with_commit_false(self):
        service, db = self.make_asi_service(totals=default_totals())
        choice = ASIChoice(increases=[ASIIncreaseItem(ability=AbilityScore.STR, amount=2)])

        await service.level_up(1, LevelUpRequest(choice=choice), make_user())

        assert service.repository.character.level == 4
        assert len(service.asi_repository.add_calls) == 1
        call = service.asi_repository.add_calls[0]
        assert call[0] == 1
        assert call[1] == 4
        assert call[2] == ASILevelChoice.ASI
        assert call[5] == [{"ability": "STR", "amount": 2}]
        assert call[6] is False
        assert db.commits == 1

    async def test_increase_is_capped_at_twenty_even_when_a_feature_raises_the_cap(self):
        service, db = self.make_asi_service(
            totals={**default_totals(), "strength_total": 21},
            caps={**dict.fromkeys(AbilityScore, ABILITY_SCORE_CAP), AbilityScore.STR: 24},
        )
        choice = ASIChoice(increases=[ASIIncreaseItem(ability=AbilityScore.STR, amount=2)])

        with pytest.raises(AbilityScoreCapExceededException):
            await service.level_up(1, LevelUpRequest(choice=choice), make_user())

        # The player's ASI is hard-capped at 20 (ABILITY_SCORE_CAP): the
        # stats service's per-ability caps (feature new_cap) are NOT consulted.
        assert service.stats_service.resolve_caps_calls == []
        assert service.asi_repository.add_calls == []

    async def test_increase_exceeding_cap_raises_and_rolls_back(self):
        service, db = self.make_asi_service(totals={**default_totals(), "strength_total": 19})
        choice = ASIChoice(increases=[ASIIncreaseItem(ability=AbilityScore.STR, amount=2)])

        with pytest.raises(AbilityScoreCapExceededException) as exc_info:
            await service.level_up(1, LevelUpRequest(choice=choice), make_user())

        assert exc_info.value.status_code == 400
        assert service.asi_repository.add_calls == []
        assert db.commits == 0
        assert db.rollbacks == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestLevelUpFeat:
    @staticmethod
    def make_feat_service(feat, known_feat_ids=(), totals=None, caps=None):
        return make_service(
            make_character(level=3),
            max_level_row=SimpleNamespace(max_level=20),
            feat=feat,
            known_feat_ids=known_feat_ids,
            totals=totals,
            caps=caps,
        )

    @staticmethod
    def plain_feat():
        return SimpleNamespace(
            id=12, ability_score_increases=[], prerequisite_ability=None, prerequisite_minimum_score=None
        )

    async def test_valid_feat_grants_grant_and_audit_row_as_asi_source(self):
        feat = self.plain_feat()
        service, db = self.make_feat_service(feat)
        request = LevelUpRequest(choice=FeatChoice(feat_id=12))

        await service.level_up(1, request, make_user())

        assert service.repository.character.level == 4
        assert service.feat_grant_repository.add_calls == [(1, 12, None, CharacterFeatSource.ASI, False)]
        audit_call = service.asi_repository.add_calls[0]
        assert audit_call[2] == ASILevelChoice.FEAT
        assert audit_call[3] == 12
        assert audit_call[6] is False
        assert db.commits == 1

    async def test_asi_offering_feat_without_choice_grants_with_none(self):
        feat = SimpleNamespace(
            id=13,
            ability_score_increases=[SimpleNamespace(id=31, ability=AbilityScore.STR, amount=1)],
            prerequisite_ability=None,
            prerequisite_minimum_score=None,
        )
        service, db = self.make_feat_service(feat)

        await service.level_up(1, LevelUpRequest(choice=FeatChoice(feat_id=13)), make_user())

        assert service.feat_grant_repository.add_calls == [(1, 13, None, CharacterFeatSource.ASI, False)]
        assert db.commits == 1

    async def test_unknown_ability_score_increase_id_rejected_before_grant(self):
        feat = SimpleNamespace(
            id=13,
            ability_score_increases=[SimpleNamespace(id=31, ability=AbilityScore.STR, amount=1)],
            prerequisite_ability=None,
            prerequisite_minimum_score=None,
        )
        service, _ = self.make_feat_service(feat)

        with pytest.raises(InvalidAbilityScoreIncreaseException):
            await service.level_up(
                1, LevelUpRequest(choice=FeatChoice(feat_id=13, ability_score_increase_id=99)), make_user()
            )

        assert service.feat_grant_repository.add_calls == []

    async def test_feat_grant_does_not_enforce_ability_score_cap(self):
        feat = SimpleNamespace(
            id=13,
            ability_score_increases=[SimpleNamespace(id=31, ability=AbilityScore.STR, amount=1)],
            prerequisite_ability=None,
            prerequisite_minimum_score=None,
        )
        service, _ = self.make_feat_service(feat, totals={**default_totals(), "strength_total": 20})

        await service.level_up(
            1, LevelUpRequest(choice=FeatChoice(feat_id=13, ability_score_increase_id=31)), make_user()
        )

        assert service.feat_grant_repository.add_calls == [(1, 13, 31, CharacterFeatSource.ASI, False)]

    async def test_unmet_prerequisite_rejected(self):
        feat = SimpleNamespace(
            id=14,
            ability_score_increases=[],
            prerequisite_ability=AbilityScore.STR,
            prerequisite_minimum_score=18,
        )
        service, _ = self.make_feat_service(feat)

        with pytest.raises(FeatPrerequisiteNotMetException):
            await service.level_up(1, LevelUpRequest(choice=FeatChoice(feat_id=14)), make_user())

        assert service.feat_grant_repository.add_calls == []

    async def test_met_prerequisite_allows_grant(self):
        feat = SimpleNamespace(
            id=14,
            ability_score_increases=[],
            prerequisite_ability=AbilityScore.STR,
            prerequisite_minimum_score=13,
        )
        service, _ = self.make_feat_service(feat)

        await service.level_up(1, LevelUpRequest(choice=FeatChoice(feat_id=14)), make_user())

        assert service.feat_grant_repository.add_calls[0][:2] == (1, 14)

    async def test_already_known_feat_conflicts(self):
        service, _ = self.make_feat_service(self.plain_feat(), known_feat_ids={12})

        with pytest.raises(CharacterFeatAlreadyKnownException):
            await service.level_up(1, LevelUpRequest(choice=FeatChoice(feat_id=12)), make_user())

        assert service.feat_grant_repository.add_calls == []

    async def test_unknown_feat_not_found(self):
        service, _ = self.make_feat_service(None)

        with pytest.raises(FeatNotFoundException):
            await service.level_up(1, LevelUpRequest(choice=FeatChoice(feat_id=99)), make_user())


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetSubclass:
    async def test_set_subclass_assigns_syncs_and_commits_once(self):
        character = make_character(subclass_id=None)
        service, db = make_service(character, subclass_row=SimpleNamespace(id=7, class_id=1))

        await service.set_subclass(1, SubclassChange(subclass_id=7), make_user())

        assert character.subclass_id == 7
        assert db.commits == 1
        assert service.stats_service.refresh_calls == [character]
        assert service.repository.db is db

    async def test_subclass_of_other_class_raises_without_writes(self):
        service, db = make_service(subclass_row=None)

        with pytest.raises(SubclassNotFoundException):
            await service.set_subclass(1, SubclassChange(subclass_id=7), make_user())

        assert db.commits == 0

    async def test_second_patch_while_set_overwrites_without_conflict(self):
        character = make_character(subclass_id=7)
        service, db = make_service(character, subclass_row=SimpleNamespace(id=9, class_id=1))

        await service.set_subclass(1, SubclassChange(subclass_id=9), make_user())

        assert character.subclass_id == 9
        assert db.commits == 1

    async def test_clearing_subclass_skips_lookup(self):
        character = make_character(subclass_id=7)
        service, _ = make_service(character)

        await service.set_subclass(1, SubclassChange(subclass_id=None), make_user())

        assert character.subclass_id is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetSubrace:
    async def test_set_subrace_assigns_syncs_and_commits_once(self):
        character = make_character(race_id=5, subrace_id=None)
        service, db = make_service(character, subrace_row=SimpleNamespace(id=2, race_id=5))

        await service.set_subrace(1, SubraceChange(subrace_id=2), make_user())

        assert character.subrace_id == 2
        assert db.commits == 1
        assert service.stats_service.refresh_calls == [character]

    async def test_subrace_of_other_race_raises(self):
        service, _ = make_service(subrace_row=None)

        with pytest.raises(SubraceNotFoundException):
            await service.set_subrace(1, SubraceChange(subrace_id=2), make_user())

    async def test_subrace_without_race_raises(self):
        character = make_character(race_id=None)
        service, _ = make_service(character, subrace_row=SimpleNamespace(id=2, race_id=5))

        with pytest.raises(SubraceNotFoundException):
            await service.set_subrace(1, SubraceChange(subrace_id=2), make_user())


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetBackground:
    def make_background_service(self, character=None, background=None, item_entries=None, execute_results=None):
        character = character or make_character(background_id=None)
        db = FakeAsyncSession(execute_results=execute_results)
        service = CharacterProgressionService(db)
        service.repository = FakeCharacterRepository(db, character)
        service.character_service = FakeCharacterService()
        service.class_repository = FakeClassRepository()
        service.race_repository = FakeRaceRepository()
        service.background_repository = FakeBackgroundRepository(background=background)
        service.item_repository = FakeItemRepository(entries=item_entries)
        service.feat_repository = FakeFeatRepository()
        service.feat_grant_repository = FakeFeatGrantRepository()
        service.asi_repository = FakeASIRepository()
        service.max_level_repository = FakeMaxLevelRepository(row=SimpleNamespace(max_level=20))
        service.stats_service = FakeStatsService()
        return service, db

    async def test_sets_background_and_grants_skills_equipment_features(self):
        existing_skill_rows = [(10,)]
        existing_stack = SimpleNamespace(item_id=100, quantity=1)
        background = SimpleNamespace(
            id=3,
            granted_skills=[SimpleNamespace(id=10), SimpleNamespace(id=11)],
        )
        service, db = self.make_background_service(
            background=background,
            item_entries=[SimpleNamespace(item_id=100, quantity=2)],
            execute_results=[FakeResult(existing_skill_rows), FakeResult([existing_stack])],
        )
        character = service.repository.character

        await service.set_background(1, BackgroundChange(background_id=3), make_user())

        assert character.background_id == 3
        added_proficiencies = [row for row in db.added if isinstance(row, CharacterSkillProficiency)]
        assert [row.skill_id for row in added_proficiencies] == [11]
        assert all(row.is_expertise is False for row in added_proficiencies)
        assert existing_stack.quantity == 3
        assert db.commits == 1
        assert service.stats_service.refresh_calls == [character]

    async def test_background_already_set_conflicts_with_409(self):
        character = make_character(background_id=3)
        service, db = self.make_background_service(character=character)

        with pytest.raises(BackgroundAlreadySetException) as exc_info:
            await service.set_background(1, BackgroundChange(background_id=4), make_user())

        assert exc_info.value.status_code == 409
        assert db.commits == 0

    async def test_unknown_background_not_found(self):
        service, db = self.make_background_service(background=None)

        with pytest.raises(BackgroundNotFoundException):
            await service.set_background(1, BackgroundChange(background_id=99), make_user())

        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRebuildCharacter:
    @staticmethod
    def make_rebuild_class_row(**overrides):
        base = {
            "id": 2,
            "hit_dice": SimpleNamespace(value="D6"),
            "available_skills": [SimpleNamespace(id=10), SimpleNamespace(id=11)],
            "skill_choice_count": 2,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    @staticmethod
    def make_data(**overrides):
        base = {
            "class_id": 2,
            "subclass_id": None,
            "race_id": 7,
            "subrace_id": None,
            "background_id": None,
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
            "max_hp": 6,
            "skill_ids": [],
            "asi_choices": [],
        }
        base.update(overrides)
        return CharacterRebuildRequest(**base)

    def make_ready_service(self, **kwargs):
        character = kwargs.pop("character", None) or make_character(level=1, max_hp=10)
        class_row = kwargs.pop("class_row", self.make_rebuild_class_row())
        race = kwargs.pop("race", SimpleNamespace(id=7, granted_skills=[]))
        return make_service(character, class_row=class_row, race=race, **kwargs)

    async def test_rebuild_replaces_build_fields_and_recomputes_derived_state(self):
        race = SimpleNamespace(id=7, granted_skills=[SimpleNamespace(id=20)])
        background = SimpleNamespace(id=9, granted_skills=[SimpleNamespace(id=21)])
        service, db = self.make_ready_service(
            character=make_character(level=1, max_hp=99),
            race=race,
            background=background,
            totals={**default_totals(), "constitution_total": 14},
        )
        character = service.repository.character
        data = self.make_data(background_id=9, constitution=14, max_hp=8, skill_ids=[10])

        await service.rebuild_character(1, data, make_user())

        assert (character.class_id, character.race_id, character.background_id) == (2, 7, 9)
        assert character.subclass_id is None
        assert character.subrace_id is None
        assert character.constitution == 14

        added_proficiencies = [row for row in db.added if isinstance(row, CharacterSkillProficiency)]
        assert {row.skill_id for row in added_proficiencies} == {10, 20, 21}
        assert all(row.is_expertise is False for row in added_proficiencies)

        # level 1 is fixed at die(6) + con mod(2) = 8 — the only legal value.
        assert character.max_hp == 8
        assert character.current_hp == 8
        assert character.temp_hp == 0

        assert service.character_spell_repository.clear_calls == [(1, False)]
        assert service.character_service.reapply_calls == [(1, False)]
        assert service.feat_grant_repository.remove_by_source_calls == [(1, CharacterFeatSource.ASI, False)]
        assert service.asi_repository.clear_calls == [(1, False)]
        assert service.stats_service.refresh_calls == [character]
        assert db.commits == 1
        assert db.rollbacks == 0

    async def test_reached_asi_choices_are_replaced_and_applied_in_level_order(self):
        service, db = self.make_ready_service(
            character=make_character(level=5, max_hp=99),
            totals={**default_totals(), "constitution_total": 10},
        )
        data = self.make_data(
            max_hp=14,
            asi_choices=[
                {"class_level": 4, "choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            ],
        )

        await service.rebuild_character(1, data, make_user())

        assert len(service.asi_repository.add_calls) == 1
        call = service.asi_repository.add_calls[0]
        assert call[1] == 4
        assert call[5] == [{"ability": "STR", "amount": 2}]
        assert service.feat_grant_repository.remove_by_source_calls == [(1, CharacterFeatSource.ASI, False)]
        assert service.asi_repository.clear_calls == [(1, False)]
        assert db.commits == 1

    async def test_missing_reached_asi_choice_rejected(self):
        service, db = self.make_ready_service(character=make_character(level=5, max_hp=99))
        data = self.make_data(max_hp=14, asi_choices=[])

        with pytest.raises(RebuildAsiChoicesMismatchException):
            await service.rebuild_character(1, data, make_user())

        assert db.commits == 0

    async def test_asi_choice_for_unreached_level_rejected(self):
        service, db = self.make_ready_service(character=make_character(level=3, max_hp=99))
        data = self.make_data(
            max_hp=8,
            asi_choices=[
                {"class_level": 4, "choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            ],
        )

        with pytest.raises(RebuildAsiChoicesMismatchException):
            await service.rebuild_character(1, data, make_user())

        assert db.commits == 0

    async def test_max_hp_below_minimum_rejected(self):
        service, db = self.make_ready_service(
            character=make_character(level=1, max_hp=99),
            totals={**default_totals(), "constitution_total": 10},
        )
        data = self.make_data(max_hp=1)  # level 1 is fixed at die(6) + con(0) = 6

        with pytest.raises(InvalidRebuildMaxHpException):
            await service.rebuild_character(1, data, make_user())

        assert db.commits == 0
        assert db.rollbacks == 1

    async def test_max_hp_above_maximum_rejected(self):
        service, db = self.make_ready_service(
            character=make_character(level=1, max_hp=99),
            totals={**default_totals(), "constitution_total": 10},
        )
        data = self.make_data(max_hp=100)

        with pytest.raises(InvalidRebuildMaxHpException):
            await service.rebuild_character(1, data, make_user())

        assert db.commits == 0

    async def test_unknown_class_raises_without_writes(self):
        service, db = self.make_ready_service(class_row=None)

        with pytest.raises(ClassNotFoundException):
            await service.rebuild_character(1, self.make_data(class_id=99), make_user())

        assert db.commits == 0

    async def test_unknown_subclass_raises(self):
        service, db = self.make_ready_service(subclass_row=None)

        with pytest.raises(SubclassNotFoundException):
            await service.rebuild_character(1, self.make_data(subclass_id=77), make_user())

        assert db.commits == 0

    async def test_unknown_race_raises(self):
        service, db = self.make_ready_service(race_exists=False)

        with pytest.raises(RaceNotFoundException):
            await service.rebuild_character(1, self.make_data(race_id=55), make_user())

        assert db.commits == 0

    async def test_subrace_of_other_race_raises(self):
        service, db = self.make_ready_service(subrace_row=None)

        with pytest.raises(SubraceNotFoundException):
            await service.rebuild_character(1, self.make_data(subrace_id=2), make_user())

        assert db.commits == 0

    async def test_unknown_background_raises(self):
        service, db = self.make_ready_service(background_exists=False)

        with pytest.raises(BackgroundNotFoundException):
            await service.rebuild_character(1, self.make_data(background_id=42), make_user())

        assert db.commits == 0

    async def test_too_many_skill_choices_rejected(self):
        service, db = self.make_ready_service()

        with pytest.raises(TooManySkillChoicesException):
            await service.rebuild_character(1, self.make_data(skill_ids=[10, 11, 12]), make_user())

        assert db.commits == 0

    async def test_skill_not_available_for_class_rejected(self):
        service, db = self.make_ready_service()

        with pytest.raises(SkillNotAvailableForClassException):
            await service.rebuild_character(1, self.make_data(skill_ids=[999]), make_user())

        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsiChoicesAudit:
    async def test_get_asi_choices_returns_audit_rows(self):
        choice_row = SimpleNamespace(
            id=1,
            character_id=1,
            class_level=4,
            choice_type=ASILevelChoice.ASI,
            feat_id=None,
            ability_score_increase_id=None,
            increases=[SimpleNamespace(ability=AbilityScore.STR, amount=2)],
        )
        service, _ = make_service(asi_choices=[choice_row])

        choices = await service.get_asi_choices(1, make_user())

        assert len(choices) == 1
        assert choices[0].class_level == 4
        assert choices[0].choice_type == ASILevelChoice.ASI
        assert choices[0].increases[0].ability == AbilityScore.STR
