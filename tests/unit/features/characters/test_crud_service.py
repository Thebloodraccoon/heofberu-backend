"""
Unit tests for CharacterCrudService (one-shot creation contract, PATCH/delete).

Exercises ``CharacterService.create_character`` against composition-style
fakes: every collaborator repository/service is replaced with a recording
stand-in, the session is a ``FakeAsyncSession``, and a shared event log
asserts cross-collaborator ORDER (feature sync before starting-HP
math, cache purge after the atomic commit). No database, no Redis.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest

from app.constants import (
    AbilityScore,
    DiceType,
    FeatureSourceType,
    UserRole,
)
from app.features.characters.ability_score.calculator import DerivedStats
from app.features.characters.crud import service as crud_service_module
from app.features.characters.crud.exceptions import (
    ItemChoiceNotAvailableException,
    ItemChoicesWithoutGroupsException,
    SkillNotAvailableForClassException,
    TooFewItemChoicesException,
    TooManySkillChoicesException,
)
from app.features.characters.crud.service import CharacterService
from app.features.characters.exceptions import BackgroundNotFoundException, CharacterAccessDeniedException
from app.features.characters.schemas import CharacterCreate, CharacterUpdate
from app.features.classes.exceptions import ClassNotFoundException
from app.features.races.exceptions import RaceNotFoundException
from app.features.users.schemas import UserResponse
from app.models import Character, CharacterSkillProficiency
from app.models.character_item_model import CharacterItem
from tests.unit.fakes import FakeAsyncSession, FakeRepository


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    """Stop generic cache invalidation from touching Redis."""
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


def make_user(user_id=7):
    return UserResponse(
        id=user_id,
        username="player",
        email="player@example.com",
        role=UserRole.PLAYER,
        created_at=datetime(2026, 1, 1),
    )


def make_class(**overrides):
    fields = {
        "id": 1,
        "name": "Fighter",
        "hit_dice": DiceType.D10,
        "skill_choice_count": 2,
        "available_skills": [SimpleNamespace(id=1), SimpleNamespace(id=2)],
        "saving_throws": [
            SimpleNamespace(ability=AbilityScore.STR),
            SimpleNamespace(ability=AbilityScore.CON),
        ],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_background():
    return SimpleNamespace(id=3, granted_skills=[SimpleNamespace(id=2)])


def make_race():
    return SimpleNamespace(id=5, granted_skills=[SimpleNamespace(id=3)])


def make_create_payload(**overrides):
    payload = {
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "background_id": 3,
        "skill_ids": [1],
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }
    payload.update(overrides)
    return CharacterCreate(**payload)


def make_owned_character(owner_id=7, character_id=5):
    return Character(
        id=character_id,
        owner_id=owner_id,
        name="Grog",
        class_id=1,
        race_id=5,
        level=1,
        current_hp=10,
        max_hp=10,
        temp_hp=0,
        speed=30,
        armor_class=10,
        shield=0,
        inspiration=False,
        notes="",
        personality_traits="",
        ideals="",
        bonds="",
        flaws="",
        money_gold=0,
        money_silver=0,
        money_copper=0,
        strength=14,
        dexterity=10,
        constitution=12,
        intelligence=10,
        wisdom=10,
        charisma=10,
    )


class RecordingSession(FakeAsyncSession):
    """FakeAsyncSession that logs commits into the shared event list."""

    def __init__(self, events):
        super().__init__()
        self.events = events

    async def commit(self):
        self.events.append("commit")
        await super().commit()


class FakeCharacterRepository(FakeRepository):
    """Character repository stand-in that attaches the eager-loaded class."""

    def __init__(self, db, existing_by_id=None, character_class=None, events=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Character)
        self.character_class_on_create = character_class
        self.events = events
        self.last_create_payload = None
        self.last_update_fields = None

    async def create(self, payload, *, commit=True):
        if self.events is not None:
            self.events.append("create_row")
        self.last_create_payload = dict(payload)
        row = await super().create(payload, commit=commit)
        row.character_class = self.character_class_on_create
        return row

    async def update(self, db_obj, update_data, *, refresh=False):
        self.last_update_fields = dict(update_data)
        return await super().update(db_obj, update_data, refresh=refresh)


class FakeClassRepository:
    def __init__(self, character_class, class_exists=True):
        self.character_class = character_class
        self.class_exists = class_exists
        self.slot_progression_calls = []

    async def exists_by_id(self, class_id):
        return self.class_exists

    async def get_subclass(self, class_id, subclass_id):
        return SimpleNamespace(id=subclass_id)

    async def get_by_id(self, class_id):
        return self.character_class

    async def get_spell_slot_progression(self, class_id, level):
        self.slot_progression_calls.append((class_id, level))
        return {}


class FakeRaceRepository:
    def __init__(self, race, race_exists=True):
        self.race = race
        self.race_exists = race_exists

    async def exists_by_id(self, race_id):
        return self.race_exists

    async def get_subrace(self, race_id, subrace_id):
        return SimpleNamespace(id=subrace_id)

    async def get_by_id(self, race_id):
        return self.race


class FakeBackgroundRepo:
    def __init__(self, background, background_exists=True):
        self.background = background
        self.background_exists = background_exists

    async def exists_by_id(self, background_id):
        return self.background_exists

    async def get_by_id(self, background_id):
        return self.background


class FakeFeatGrantRepository:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def add_character_feat(self, character_id, feat_id, asi_id, *, source_type, commit):
        self.events.append("feat_grant")
        self.calls.append((character_id, feat_id, asi_id, source_type, commit))


class FakeAsiRepository:
    def __init__(self):
        self.calls = []

    async def add(
        self,
        character_id,
        class_level,
        choice,
        *,
        feat_id=None,
        ability_score_increase_id=None,
        commit=True,
    ):
        self.calls.append((character_id, class_level, choice, feat_id, ability_score_increase_id, commit))


class FakeMaxLevelRepository:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def create_for_character(self, character_id, level, *, commit):
        self.events.append("seed_max_level")
        self.calls.append((character_id, level, commit))


class FakeSpellSlotRepository:
    def __init__(self):
        self.calls = []

    async def apply_spell_slot_progression(self, character_id, slots_by_level, *, commit=True):
        self.calls.append((character_id, slots_by_level, commit))


class FakeItemRepository:
    def __init__(self, events, entries=None, choice_groups=None):
        self.events = events
        self.entries = entries or []
        self.choice_groups = choice_groups or []
        self.source_calls = []
        self.choice_group_calls = []

    async def get_source_items_for_sources(self, sources):
        self.source_calls.append(sources)
        self.events.append("grant_equipment")
        return self.entries

    async def get_choice_groups_for_sources(self, sources):
        self.choice_group_calls.append(sources)
        return self.choice_groups


class FakeStatsService:
    """Records compute calls in the shared event log (HP-math marker)."""

    def __init__(self, events, constitution_total=14):
        self.events = events
        self.constitution_total = constitution_total
        self.compute_calls = []

    async def compute(self, character):
        self.events.append("compute_hp")
        self.compute_calls.append(character)
        return {"constitution_total": self.constitution_total}

    async def resolve_ability_caps(self, character):
        return dict.fromkeys(AbilityScore, 20)

    async def for_response(self, character, *, refresh=False):
        return None

    async def compute_derived(self, character):
        return DerivedStats(hit_dice="D10", speed=30)


def make_service(
    monkeypatch=None,
    events=None,
    *,
    character_class=None,
    background=None,
    race=None,
    class_exists=True,
    race_exists=True,
    background_exists=True,
    constitution_total=14,
    equipment_entries=None,
    choice_groups=None,
    existing_characters=None,
):
    db = RecordingSession(events)
    character_class = character_class if character_class is not None else make_class()
    service = CharacterService(db)

    service.repository = FakeCharacterRepository(
        db,
        existing_by_id=existing_characters or {},
        character_class=character_class,
        events=events,
    )
    service.class_repository = FakeClassRepository(character_class, class_exists=class_exists)
    service.race_repository = FakeRaceRepository(race if race is not None else make_race(), race_exists=race_exists)
    service.background_repository = FakeBackgroundRepo(
        background if background is not None else make_background(),
        background_exists=background_exists,
    )
    service.item_repository = FakeItemRepository(events, entries=equipment_entries, choice_groups=choice_groups)
    service.stats_service = FakeStatsService(events, constitution_total=constitution_total)
    service.feat_grant_repository = FakeFeatGrantRepository(events)
    service.asi_repository = FakeAsiRepository()
    service.max_level_repository = FakeMaxLevelRepository(events)
    service.character_spell_slot_repository = FakeSpellSlotRepository()

    if monkeypatch is not None:

        async def fake_sync(db_arg, character):
            events.append("sync_features")

        async def fake_invalidate(character_id):
            events.append("invalidate")

        monkeypatch.setattr(crud_service_module, "sync_progression_features", fake_sync)
        monkeypatch.setattr(crud_service_module, "invalidate_character_cache", fake_invalidate)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestCharacterCreateSchema:
    async def test_extra_forbid_rejects_stale_level_and_max_hp(self):
        with pytest.raises(ValidationError):
            make_create_payload(level=3)
        with pytest.raises(ValidationError):
            make_create_payload(max_hp=20)

    async def test_creation_without_feat_is_valid(self):
        """The origin-feat contract was removed: no feat is granted at creation."""

        payload = {
            "name": "Grog",
            "class_id": 1,
            "strength": 14,
            "dexterity": 10,
            "constitution": 12,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
        }
        assert CharacterCreate(**payload).name == "Grog"
        assert not hasattr(CharacterCreate(**payload), "feat_id")

    async def test_feat_id_field_is_rejected_as_extra(self):
        with pytest.raises(ValidationError):
            make_create_payload(feat_id=9)

    async def test_duplicate_skill_ids_rejected(self):
        with pytest.raises(ValidationError):
            make_create_payload(skill_ids=[1, 1])

    async def test_duplicate_item_choice_ids_rejected(self):
        with pytest.raises(ValidationError):
            make_create_payload(item_choice_ids=[100, 100])


@pytest.mark.unit
@pytest.mark.asyncio
class TestValidateChosenSkills:
    async def test_unknown_skill_raises_skill_not_available(self):
        service, _ = make_service(None, [])

        with pytest.raises(SkillNotAvailableForClassException) as exc_info:
            service._validate_chosen_skills([99], make_class())

        assert exc_info.value.skill_id == 99
        assert exc_info.value.class_id == 1

    async def test_too_many_choices_raises(self):
        service, _ = make_service(None, [])
        klass = make_class(skill_choice_count=2, available_skills=[SimpleNamespace(id=i) for i in range(1, 5)])

        with pytest.raises(TooManySkillChoicesException) as exc_info:
            service._validate_chosen_skills([1, 2, 3], klass)

        assert exc_info.value.allowed == 2
        assert exc_info.value.requested == 3

    async def test_empty_choices_pass_without_validation(self):
        service, _ = make_service(None, [])

        assert service._validate_chosen_skills([], make_class()) == []


def make_choice_group(group_id=1, pick_count=1, options=None):
    return SimpleNamespace(id=group_id, pick_count=pick_count, options=options or [])


def make_choice_option(option_id=100, group_id=1, item_id=20, quantity=1):
    return SimpleNamespace(id=option_id, group_id=group_id, item_id=item_id, quantity=quantity)


@pytest.mark.unit
@pytest.mark.asyncio
class TestResolveItemChoices:
    async def test_no_sources_and_empty_choice_returns_empty(self):
        service, _ = make_service(None, [])

        assert await service._resolve_item_choices(None, None, []) == []

    async def test_choice_without_sources_raises(self):
        service, _ = make_service(None, [])

        with pytest.raises(ItemChoicesWithoutGroupsException):
            await service._resolve_item_choices(None, None, [100])

    async def test_choice_when_sources_define_no_groups_raises(self):
        service, _ = make_service(None, [], choice_groups=[])

        with pytest.raises(ItemChoicesWithoutGroupsException):
            await service._resolve_item_choices(1, 3, [100])

    async def test_foreign_option_raises(self):
        group = make_choice_group(
            options=[make_choice_option(option_id=100), make_choice_option(option_id=101)]
        )
        service, _ = make_service(None, [], choice_groups=[group])

        with pytest.raises(ItemChoiceNotAvailableException) as exc_info:
            await service._resolve_item_choices(1, 3, [999])

        assert exc_info.value.option_id == 999

    async def test_exactly_pick_count_is_accepted(self):
        option_a = make_choice_option(option_id=100, item_id=20)
        option_b = make_choice_option(option_id=101, item_id=21)
        group = make_choice_group(pick_count=1, options=[option_a, option_b])
        service, _ = make_service(None, [], choice_groups=[group])

        resolved = await service._resolve_item_choices(1, None, [100])

        assert resolved == [option_a]
        assert service.item_repository.choice_group_calls == [[(FeatureSourceType.CLASS, 1)]]

    async def test_fewer_than_pick_count_raises(self):
        group = make_choice_group(
            pick_count=2,
            options=[
                make_choice_option(option_id=100, item_id=20),
                make_choice_option(option_id=101, item_id=21),
                make_choice_option(option_id=102, item_id=22),
            ],
        )
        service, _ = make_service(None, [], choice_groups=[group])

        with pytest.raises(TooFewItemChoicesException) as exc_info:
            await service._resolve_item_choices(1, None, [100])

        assert exc_info.value.group_id == 1
        assert exc_info.value.pick_count == 2
        assert exc_info.value.chosen == 1

    async def test_every_group_must_be_answered(self):
        group_a = make_choice_group(
            group_id=1,
            pick_count=1,
            options=[
                make_choice_option(option_id=100, group_id=1, item_id=20),
                make_choice_option(option_id=101, group_id=1, item_id=21),
            ],
        )
        group_b = make_choice_group(
            group_id=2,
            pick_count=1,
            options=[
                make_choice_option(option_id=200, group_id=2, item_id=22),
                make_choice_option(option_id=201, group_id=2, item_id=23),
            ],
        )
        service, _ = make_service(None, [], choice_groups=[group_a, group_b])

        with pytest.raises(TooFewItemChoicesException) as exc_info:
            await service._resolve_item_choices(1, None, [100])

        assert exc_info.value.group_id == 2

    async def test_class_and_background_groups_are_both_resolved(self):
        class_option = make_choice_option(option_id=100, group_id=1, item_id=20)
        background_option = make_choice_option(option_id=200, group_id=2, item_id=22)
        groups = [
            make_choice_group(group_id=1, pick_count=1, options=[class_option]),
            make_choice_group(group_id=2, pick_count=1, options=[background_option]),
        ]
        service, _ = make_service(None, [], choice_groups=groups)

        resolved = await service._resolve_item_choices(1, 3, [100, 200])

        assert resolved == [class_option, background_option]
        assert service.item_repository.choice_group_calls == [
            [(FeatureSourceType.CLASS, 1), (FeatureSourceType.BACKGROUND, 3)]
        ]


@pytest.mark.unit
@pytest.mark.asyncio
class TestComputeStartingMaxHp:
    async def test_hit_die_faces_plus_con_modifier(self):
        service, _ = make_service(None, [], constitution_total=14)

        result = await service._compute_starting_max_hp(SimpleNamespace(id=1), make_class())

        assert result == 12

    async def test_clamped_to_at_least_one(self):
        service, _ = make_service(None, [], constitution_total=-4)
        klass = make_class(hit_dice=DiceType.D6)

        result = await service._compute_starting_max_hp(SimpleNamespace(id=1), klass)

        assert result == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateCharacterHappyPath:
    async def test_writes_the_full_creation_contract(self, monkeypatch):
        events = []
        equipment_entries = [
            SimpleNamespace(item_id=10, quantity=1),
            SimpleNamespace(item_id=10, quantity=2),
            SimpleNamespace(item_id=11, quantity=1),
        ]
        service, db = make_service(monkeypatch, events, equipment_entries=equipment_entries, constitution_total=14)
        user = make_user()

        result = await service.create_character(make_create_payload(), user)

        character = service.repository.created[0]
        assert character.level == 1
        assert character.temp_hp == 0
        assert character.owner_id == user.id
        assert "skill_ids" not in service.repository.last_create_payload
        assert character.current_hp == 12
        assert character.max_hp == 12

        proficiency_rows = [row for row in db.added if isinstance(row, CharacterSkillProficiency)]
        assert sorted(row.skill_id for row in proficiency_rows) == [1, 2, 3]
        assert all(row.is_expertise is False for row in proficiency_rows)
        assert all(row.character_id == 1 for row in proficiency_rows)

        item_rows = [row for row in db.added if isinstance(row, CharacterItem)]
        assert sorted((row.item_id, row.quantity) for row in item_rows) == [(10, 3), (11, 1)]
        assert service.item_repository.source_calls == [
            [(FeatureSourceType.CLASS, 1), (FeatureSourceType.BACKGROUND, 3)]
        ]

        assert service.max_level_repository.calls == [(1, 1, False)]
        assert service.class_repository.slot_progression_calls == [(1, 1)]
        assert service.character_spell_slot_repository.calls == [(1, {}, False)]
        assert service.feat_grant_repository.calls == []
        assert service.asi_repository.calls == []

        assert db.commits == 1
        assert db.flushes == 4
        assert result.id == 1
        assert result.level == 1
        assert result.temp_hp == 0
        assert result.current_hp == 12
        assert result.max_hp == 12
        assert [st.ability for st in result.saving_throw_proficiencies] == [AbilityScore.STR, AbilityScore.CON]
        assert result.hit_dice == "D10"
        assert result.speed == 30

    async def test_creation_grants_chosen_item_options_merged_with_guaranteed(self, monkeypatch):
        events = []
        guaranteed = [SimpleNamespace(item_id=10, quantity=1)]
        option = make_choice_option(option_id=100, group_id=1, item_id=10, quantity=2)
        group = make_choice_group(
            pick_count=1, options=[option, make_choice_option(option_id=101, group_id=1, item_id=21)]
        )
        service, db = make_service(monkeypatch, events, equipment_entries=guaranteed, choice_groups=[group])
        user = make_user()

        result = await service.create_character(make_create_payload(item_choice_ids=[100]), user)

        # Item 10 is granted both as guaranteed equipment (qty 1) and as
        # the chosen option (qty 2) — merged into a single stack of three.
        item_rows = [row for row in db.added if isinstance(row, CharacterItem)]
        assert sorted((row.item_id, row.quantity) for row in item_rows) == [(10, 3)]
        assert "item_choice_ids" not in service.repository.last_create_payload
        assert service.item_repository.choice_group_calls == [
            [(FeatureSourceType.CLASS, 1), (FeatureSourceType.BACKGROUND, 3)]
        ]
        assert result.ability_scores is None

    async def test_creation_rejects_unanswered_choice_group(self, monkeypatch):
        group = make_choice_group(
            pick_count=1,
            options=[
                make_choice_option(option_id=100, group_id=1, item_id=20),
                make_choice_option(option_id=101, group_id=1, item_id=21),
            ],
        )
        service, db = make_service(monkeypatch, [], choice_groups=[group])
        user = make_user()

        with pytest.raises(TooFewItemChoicesException):
            await service.create_character(make_create_payload(item_choice_ids=[]), user)

        assert not service.repository.created
        assert db.added == []

    async def test_order_feature_sync_before_hp_math_commit_before_invalidate(self, monkeypatch):
        events = []
        service, _ = make_service(monkeypatch, events)

        await service.create_character(make_create_payload(), make_user())

        assert "feat_grant" not in events
        assert events.index("sync_features") < events.index("compute_hp")
        assert events.index("compute_hp") < events.index("grant_equipment")
        assert events.index("commit") < events.index("invalidate")


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateCharacterReferenceValidation:
    async def test_missing_class_reference_raises(self, monkeypatch):
        service, db = make_service(monkeypatch, [], class_exists=False)

        with pytest.raises(ClassNotFoundException):
            await service.create_character(make_create_payload(), make_user())

        assert db.commits == 0
        assert service.repository.created == []

    async def test_missing_race_reference_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], race_exists=False)

        with pytest.raises(RaceNotFoundException):
            await service.create_character(make_create_payload(), make_user())

    async def test_missing_background_reference_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], background_exists=False)

        with pytest.raises(BackgroundNotFoundException):
            await service.create_character(make_create_payload(), make_user())


@pytest.mark.unit
@pytest.mark.asyncio
class TestToResponseSavingThrows:
    async def test_saving_throws_derived_from_the_class_not_stored(self, monkeypatch):
        service, _ = make_service(None, [])
        character = SimpleNamespace(
            id=1,
            owner_id=7,
            name="Grog",
            class_id=1,
            subclass_id=None,
            race_id=5,
            subrace_id=None,
            background_id=3,
            armor_class=10,
            shield=0,
            notes="",
            personality_traits="",
            ideals="",
            bonds="",
            flaws="",
            money_gold=0,
            money_silver=0,
            money_copper=0,
            level=1,
            current_hp=12,
            max_hp=12,
            temp_hp=0,
            character_class=make_class(saving_throws=[SimpleNamespace(ability=AbilityScore.WIS)]),
        )
        cache_row = SimpleNamespace(
            strength_total=14,
            dexterity_total=10,
            constitution_total=12,
            intelligence_total=10,
            wisdom_total=11,
            charisma_total=10,
        )

        result = await service._to_response(
            character,
            cache_row=cache_row,
            derived=DerivedStats(hit_dice="D8", speed=25),
        )

        assert [st.ability for st in result.saving_throw_proficiencies] == [AbilityScore.WIS]
        assert not hasattr(character, "saving_throw_proficiencies")
        assert result.hit_dice == "D8"
        assert result.speed == 25
        assert result.ability_scores.wisdom_total == 11


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateAndDelete:
    async def test_update_applies_only_provided_fields(self, monkeypatch):
        character = make_owned_character()
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})
        data = CharacterUpdate(name="NewName", armor_class=16)

        result = await service.update_character(5, data, make_user())

        assert service.repository.last_update_fields == {"name": "NewName", "armor_class": 16}
        assert result.name == "NewName"
        assert result.armor_class == 16

    async def test_update_denied_for_other_player(self, monkeypatch):
        character = make_owned_character(owner_id=7)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        with pytest.raises(CharacterAccessDeniedException):
            await service.update_character(5, CharacterUpdate(name="X"), make_user(user_id=8))

        assert service.repository.last_update_fields is None

    async def test_delete_owner_returns_true_and_removes_row(self, monkeypatch):
        character = make_owned_character(owner_id=7)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        assert await service.delete_character(5, make_user()) is True
        assert service.repository.deleted == [character]

    async def test_delete_denied_for_other_player(self, monkeypatch):
        character = make_owned_character(owner_id=7)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        with pytest.raises(CharacterAccessDeniedException):
            await service.delete_character(5, make_user(user_id=8))

        assert service.repository.deleted == []
