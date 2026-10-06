"""
Unit tests for the character crud service (creation contract, PATCH/delete, HP, rest).

Exercises ``CharacterService`` against composition-style fakes: every
collaborator repository/service is replaced with a recording stand-in, the
session is a ``FakeAsyncSession``, and a shared event log asserts
cross-collaborator ORDER (feature sync before starting-HP math, cache purge
only after the commit). No database, no Redis.
"""

from datetime import datetime
from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from app.constants import (
    AbilityScore,
    ArmorProficiency,
    DiceType,
    FeatureSourceType,
    ProficiencySourceType,
    ProficiencyType,
    UserRole,
    WeaponProficiency,
)
from app.core.base.transaction import after_commit
from app.features.characters import base as base_module
from app.features.characters.ability_score.calculator import DerivedStats
from app.features.characters.crud import creation as creation_module
from app.features.characters.crud.exceptions import (
    InvalidHpUpdateException,
    ItemChoiceNotAvailableException,
    ItemChoicesWithoutGroupsException,
    SkillNotAvailableForClassException,
    TooFewItemChoicesException,
    TooManySkillChoicesException,
)
from app.features.characters.crud.rules import starting_max_hp, validate_chosen_skills
from app.features.characters.crud.schemas import HpUpdate, RestRequest
from app.features.characters.crud.service import CharacterService
from app.features.characters.exceptions import (
    BackgroundNotFoundException,
    CharacterAccessDeniedException,
    CharacterNotFoundException,
    GmOnlyFieldException,
)
from app.features.characters.schemas import CharacterCreate, CharacterUpdate
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.races.exceptions import RaceNotFoundException, SubraceNotFoundException
from app.features.users.schemas import UserResponse
from app.models import Character
from app.models.character.character_backstory_model import CharacterBackstory
from app.models.character.character_item_model import CharacterItem
from app.models.character.character_proficiency_model import CharacterProficiency
from tests.unit.fakes import FakeAsyncSession, FakeRepository


def make_user(user_id=7, role=UserRole.PLAYER):
    return UserResponse(
        id=user_id,
        username="player",
        email="player@example.com",
        role=role,
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
        "armor_proficiencies": [
            SimpleNamespace(armor_type=ArmorProficiency.LIGHT),
            SimpleNamespace(armor_type=ArmorProficiency.MEDIUM),
        ],
        "weapon_proficiencies": [
            SimpleNamespace(weapon_category=WeaponProficiency.SIMPLE),
            SimpleNamespace(weapon_category=WeaponProficiency.MARTIAL),
        ],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_background_suggestions():
    return [
        SimpleNamespace(id=100 + i, suggestion_type=suggestion_type, text=f"{suggestion_type} text")
        for i, suggestion_type in enumerate(("PERSONALITY_TRAIT", "IDEAL", "BOND", "FLAW"))
    ]


def make_background(description=""):
    return SimpleNamespace(
        id=3,
        granted_skills=[SimpleNamespace(id=2)],
        description=description,
        suggestions=make_background_suggestions(),
    )


def make_race(**overrides):
    fields = {"id": 5, "granted_skills": [SimpleNamespace(id=3)], "speed": 30}
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_create_payload(**overrides):
    payload = {
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "background_id": 3,
        "suggestion_ids": [100, 101, 102, 103],
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


def make_owned_character(owner_id=7, character_id=5, **overrides):
    fields = {
        "id": character_id,
        "owner_id": owner_id,
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "level": 1,
        "current_hp": 10,
        "max_hp": 10,
        "temp_hp": 0,
        "speed": 30,
        "armor_class": 10,
        "shield": 0,
        "inspiration": 0,
        "notes": "",
        "personality_traits": "",
        "ideals": "",
        "bonds": "",
        "flaws": "",
        "money_gold": 0,
        "money_silver": 0,
        "money_copper": 0,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }
    fields.update(overrides)
    return Character(**fields)


class RecordingSession(FakeAsyncSession):
    """FakeAsyncSession that logs commits and rollbacks into the shared event list."""

    def __init__(self, events):
        super().__init__()
        self.events = events

    async def commit(self):
        self.events.append("commit")
        await super().commit()

    async def rollback(self):
        self.events.append("rollback")
        await super().rollback()


class FakeCharacterRepository(FakeRepository):
    """Character repository stand-in that attaches the eager-loaded class."""

    def __init__(self, db, existing_by_id=None, character_class=None, events=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Character)
        self.character_class_on_create = character_class
        self.events = events
        self.last_create_payload = None
        self.last_update_fields = None
        self.hp_updates = []

    async def create(self, payload):
        if self.events is not None:
            self.events.append("create_row")
        self.last_create_payload = dict(payload)
        row = await super().create(payload)
        row.character_class = self.character_class_on_create
        return row

    async def update(self, db_obj, update_data, *, refresh=False):
        self.last_update_fields = dict(update_data)
        return await super().update(db_obj, update_data, refresh=refresh)

    async def get_for_update(self, character_id):
        self.events.append("lock_row")
        return await self.get_by_id(character_id)

    async def update_hp(self, character, current_hp, temp_hp):
        self.hp_updates.append((current_hp, temp_hp))
        character.current_hp = current_hp
        character.temp_hp = temp_hp
        await self.flush()
        return character


class FakeClassRepository:
    def __init__(self, character_class, class_exists=True, subclass_exists=True):
        self.character_class = character_class
        self.class_exists = class_exists
        self.subclass_exists = subclass_exists
        self.slot_progression_calls = []

    async def get_subclass(self, class_id, subclass_id):
        return SimpleNamespace(id=subclass_id) if self.subclass_exists else None

    async def get_by_id(self, class_id):
        return self.character_class if self.class_exists else None

    async def get_spell_slot_progression(self, class_id, level):
        self.slot_progression_calls.append((class_id, level))
        return {}


class FakeRaceRepository:
    def __init__(self, race, race_exists=True, subrace_exists=True):
        self.race = race
        self.race_exists = race_exists
        self.subrace_exists = subrace_exists

    async def get_subrace(self, race_id, subrace_id):
        return SimpleNamespace(id=subrace_id) if self.subrace_exists else None

    async def get_by_id(self, race_id):
        return self.race if self.race_exists else None


class FakeBackgroundRepo:
    def __init__(self, background, background_exists=True):
        self.background = background
        self.background_exists = background_exists

    async def get_by_id(self, background_id):
        return self.background if self.background_exists else None


class FakeMaxLevelRepository:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def create_for_character(self, character_id, level):
        self.events.append("seed_max_level")
        self.calls.append((character_id, level))


class FakeSlotUsageRepository:
    def __init__(self):
        self.resets = []
        self.fail = False

    async def reset_all_spell_slots(self, character_id):
        if self.fail:
            raise RuntimeError("slot reset failed")
        self.resets.append(character_id)


class FakeSpellSlotRepository:
    def __init__(self):
        self.calls = []

    async def apply_spell_slot_progression(self, character_id, slots_by_level):
        self.calls.append((character_id, slots_by_level))


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
    """Records stats calls in the shared event log (starting-HP marker)."""

    def __init__(self, events, constitution_total=14):
        self.events = events
        self.constitution_total = constitution_total
        self.refresh_calls = []

    async def refresh(self, character):
        self.events.append("refresh_stats")
        self.refresh_calls.append(character)
        return SimpleNamespace(
            strength_total=14,
            dexterity_total=10,
            constitution_total=self.constitution_total,
            intelligence_total=10,
            wisdom_total=10,
            charisma_total=10,
        )

    async def get_or_stale(self, character_id):
        return None

    async def compute_derived(self, character):
        return DerivedStats(hit_dice="D10")


def make_service(
    monkeypatch=None,
    events=None,
    *,
    character_class=None,
    background=None,
    race=None,
    class_exists=True,
    subclass_exists=True,
    race_exists=True,
    subrace_exists=True,
    background_exists=True,
    constitution_total=14,
    equipment_entries=None,
    choice_groups=None,
    existing_characters=None,
):
    events = events if events is not None else []
    db = RecordingSession(events)
    character_class = character_class if character_class is not None else make_class()
    service = CharacterService(db)
    creation = service.creation

    service.repository = creation.repository = FakeCharacterRepository(
        db,
        existing_by_id=existing_characters or {},
        character_class=character_class,
        events=events,
    )
    creation.class_repository = FakeClassRepository(
        character_class, class_exists=class_exists, subclass_exists=subclass_exists
    )
    creation.race_repository = FakeRaceRepository(
        race if race is not None else make_race(), race_exists=race_exists, subrace_exists=subrace_exists
    )
    creation.background_repository = FakeBackgroundRepo(
        background if background is not None else make_background(),
        background_exists=background_exists,
    )
    creation.item_repository = FakeItemRepository(events, entries=equipment_entries, choice_groups=choice_groups)
    service.stats_service = creation.stats_service = FakeStatsService(events, constitution_total=constitution_total)
    creation.max_level_repository = FakeMaxLevelRepository(events)
    creation.spell_slot_repository = FakeSpellSlotRepository()
    service.character_spell_slot_repository = FakeSlotUsageRepository()

    if monkeypatch is not None:

        async def fake_sync(db_arg, character):
            events.append("sync_features")
            return []

        async def fake_invalidate(character_id, *, db=None):
            async def purge():
                events.append(f"invalidate:{character_id}")

            await after_commit(db, purge)

        monkeypatch.setattr(creation_module, "sync_progression_features", fake_sync)
        monkeypatch.setattr(base_module, "invalidate_character_cache", fake_invalidate)
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
class TestValidateChosenSkills:
    def test_unknown_skill_raises_skill_not_available(self):
        with pytest.raises(SkillNotAvailableForClassException) as exc_info:
            validate_chosen_skills([99], make_class())

        assert exc_info.value.skill_id == 99
        assert exc_info.value.class_id == 1

    def test_too_many_choices_raises(self):
        klass = make_class(skill_choice_count=2, available_skills=[SimpleNamespace(id=i) for i in range(1, 5)])

        with pytest.raises(TooManySkillChoicesException) as exc_info:
            validate_chosen_skills([1, 2, 3], klass)

        assert exc_info.value.allowed == 2
        assert exc_info.value.requested == 3

    def test_empty_choices_pass_without_validation(self):
        assert validate_chosen_skills([], make_class()) == []

    def test_fewer_choices_than_the_class_allows_are_accepted(self):
        assert validate_chosen_skills([1], make_class(skill_choice_count=2)) == [1]


def make_choice_group(group_id=1, pick_count=1, options=None):
    return SimpleNamespace(id=group_id, pick_count=pick_count, options=options or [])


def make_choice_option(option_id=100, group_id=1, item_id=20, quantity=1):
    return SimpleNamespace(id=option_id, group_id=group_id, item_id=item_id, quantity=quantity)


@pytest.mark.unit
@pytest.mark.asyncio
class TestResolveItemChoices:
    async def test_no_sources_and_empty_choice_returns_empty(self):
        service, _ = make_service(None, [])

        assert await service.creation._resolve_item_choices(None, None, []) == []

    async def test_choice_without_sources_raises(self):
        service, _ = make_service(None, [])

        with pytest.raises(ItemChoicesWithoutGroupsException):
            await service.creation._resolve_item_choices(None, None, [100])

    async def test_choice_when_sources_define_no_groups_raises(self):
        service, _ = make_service(None, [], choice_groups=[])

        with pytest.raises(ItemChoicesWithoutGroupsException):
            await service.creation._resolve_item_choices(1, 3, [100])

    async def test_foreign_option_raises(self):
        group = make_choice_group(options=[make_choice_option(option_id=100), make_choice_option(option_id=101)])
        service, _ = make_service(None, [], choice_groups=[group])

        with pytest.raises(ItemChoiceNotAvailableException) as exc_info:
            await service.creation._resolve_item_choices(1, 3, [999])

        assert exc_info.value.option_id == 999

    async def test_exactly_pick_count_is_accepted(self):
        option_a = make_choice_option(option_id=100, item_id=20)
        option_b = make_choice_option(option_id=101, item_id=21)
        group = make_choice_group(pick_count=1, options=[option_a, option_b])
        service, _ = make_service(None, [], choice_groups=[group])

        resolved = await service.creation._resolve_item_choices(1, None, [100])

        assert resolved == [option_a]
        assert service.creation.item_repository.choice_group_calls == [[(FeatureSourceType.CLASS, 1)]]

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
            await service.creation._resolve_item_choices(1, None, [100])

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
            await service.creation._resolve_item_choices(1, None, [100])

        assert exc_info.value.group_id == 2

    async def test_class_and_background_groups_are_both_resolved(self):
        class_option = make_choice_option(option_id=100, group_id=1, item_id=20)
        background_option = make_choice_option(option_id=200, group_id=2, item_id=22)
        groups = [
            make_choice_group(group_id=1, pick_count=1, options=[class_option]),
            make_choice_group(group_id=2, pick_count=1, options=[background_option]),
        ]
        service, _ = make_service(None, [], choice_groups=groups)

        resolved = await service.creation._resolve_item_choices(1, 3, [100, 200])

        assert resolved == [class_option, background_option]
        assert service.creation.item_repository.choice_group_calls == [
            [(FeatureSourceType.CLASS, 1), (FeatureSourceType.BACKGROUND, 3)]
        ]


@pytest.mark.unit
class TestStartingMaxHp:
    def test_hit_die_faces_plus_con_modifier(self):
        assert starting_max_hp(DiceType.D10, 14) == 12

    def test_clamped_to_at_least_one(self):
        assert starting_max_hp(DiceType.D6, -4) == 1


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

        proficiency_rows = [
            row
            for row in db.added
            if isinstance(row, CharacterProficiency) and row.proficiency_type == ProficiencyType.SKILL
        ]
        assert sorted(row.skill_id for row in proficiency_rows) == [1, 2, 3]
        assert all(row.is_expertise is False for row in proficiency_rows)
        assert all(row.character_id == 1 for row in proficiency_rows)

        saving_throw_rows = [
            row
            for row in db.added
            if isinstance(row, CharacterProficiency) and row.proficiency_type == ProficiencyType.SAVING_THROW
        ]
        assert sorted(row.ability for row in saving_throw_rows) == sorted([AbilityScore.STR, AbilityScore.CON])
        assert all(row.source_type == ProficiencySourceType.CLASS for row in saving_throw_rows)

        armor_rows = [
            row
            for row in db.added
            if isinstance(row, CharacterProficiency) and row.proficiency_type == ProficiencyType.ARMOR
        ]
        assert sorted(row.armor_type for row in armor_rows) == sorted([ArmorProficiency.LIGHT, ArmorProficiency.MEDIUM])
        assert all(row.source_type == ProficiencySourceType.CLASS for row in armor_rows)
        assert all(row.character_id == 1 for row in armor_rows)

        weapon_rows = [
            row
            for row in db.added
            if isinstance(row, CharacterProficiency) and row.proficiency_type == ProficiencyType.WEAPON
        ]
        assert sorted(row.weapon_category for row in weapon_rows) == sorted(
            [WeaponProficiency.SIMPLE, WeaponProficiency.MARTIAL]
        )
        assert all(row.source_type == ProficiencySourceType.CLASS for row in weapon_rows)
        assert all(row.character_id == 1 for row in weapon_rows)

        item_rows = [row for row in db.added if isinstance(row, CharacterItem)]
        assert sorted((row.item_id, row.quantity) for row in item_rows) == [(10, 3), (11, 1)]
        assert service.creation.item_repository.source_calls == [
            [(FeatureSourceType.CLASS, 1), (FeatureSourceType.BACKGROUND, 3)]
        ]

        assert service.creation.max_level_repository.calls == [(1, 1)]
        assert service.creation.class_repository.slot_progression_calls == [(1, 1)]
        assert service.creation.spell_slot_repository.calls == [(1, {})]
        assert service.stats_service.refresh_calls == [character]

        assert db.commits == 1
        assert result.id == 1
        assert result.level == 1
        assert result.temp_hp == 0
        assert result.current_hp == 12
        assert result.max_hp == 12
        assert result.hit_dice == "D10"
        assert result.speed == 30
        assert result.ability_scores.constitution_total == 14

    async def test_speed_is_seeded_from_the_race(self, monkeypatch):
        service, db = make_service(monkeypatch, [], race=make_race(speed=35))

        result = await service.create_character(make_create_payload(), make_user())

        assert service.repository.created[0].speed == 35
        assert result.speed == 35

    async def test_speed_falls_back_to_default_without_a_race(self, monkeypatch):
        service, db = make_service(monkeypatch, [])

        result = await service.create_character(make_create_payload(race_id=None), make_user())

        assert service.repository.created[0].speed == 30
        assert result.speed == 30

    async def test_class_with_no_armor_or_weapon_proficiencies_writes_no_rows(self, monkeypatch):
        klass = make_class(armor_proficiencies=[], weapon_proficiencies=[])
        service, db = make_service(monkeypatch, [], character_class=klass)

        await service.create_character(make_create_payload(), make_user())

        armor_or_weapon_rows = [
            row
            for row in db.added
            if isinstance(row, CharacterProficiency)
            and row.proficiency_type in (ProficiencyType.ARMOR, ProficiencyType.WEAPON)
        ]
        assert armor_or_weapon_rows == []

    async def test_creation_grants_chosen_item_options_merged_with_guaranteed(self, monkeypatch):
        guaranteed = [SimpleNamespace(item_id=10, quantity=1)]
        option = make_choice_option(option_id=100, group_id=1, item_id=10, quantity=2)
        group = make_choice_group(
            pick_count=1, options=[option, make_choice_option(option_id=101, group_id=1, item_id=21)]
        )
        service, db = make_service(monkeypatch, [], equipment_entries=guaranteed, choice_groups=[group])

        await service.create_character(make_create_payload(item_choice_ids=[100]), make_user())

        item_rows = [row for row in db.added if isinstance(row, CharacterItem)]
        assert sorted((row.item_id, row.quantity) for row in item_rows) == [(10, 3)]
        assert "item_choice_ids" not in service.repository.last_create_payload

    async def test_creation_rejects_unanswered_choice_group(self, monkeypatch):
        group = make_choice_group(
            pick_count=1,
            options=[
                make_choice_option(option_id=100, group_id=1, item_id=20),
                make_choice_option(option_id=101, group_id=1, item_id=21),
            ],
        )
        service, db = make_service(monkeypatch, [], choice_groups=[group])

        with pytest.raises(TooFewItemChoicesException):
            await service.create_character(make_create_payload(item_choice_ids=[]), make_user())

        assert not service.repository.created
        assert db.added == []

    async def test_background_description_becomes_the_backstory_capped_at_the_limit(self, monkeypatch):
        service, db = make_service(monkeypatch, [], background=make_background(description="x" * 20_000))

        await service.create_character(make_create_payload(), make_user())

        backstories = [row for row in db.added if isinstance(row, CharacterBackstory)]
        assert len(backstories) == 1
        assert len(backstories[0].content) == 12_000

    async def test_background_suggestions_replace_the_personality_fields(self, monkeypatch):
        service, _ = make_service(monkeypatch, [])

        result = await service.create_character(make_create_payload(personality_traits="mine"), make_user())

        assert result.personality_traits == "PERSONALITY_TRAIT text"
        assert result.flaws == "FLAW text"

    async def test_order_feature_sync_before_hp_math_all_before_the_single_commit(self, monkeypatch):
        events = []
        service, _ = make_service(monkeypatch, events)

        await service.create_character(make_create_payload(), make_user())

        assert events.index("sync_features") < events.index("refresh_stats")
        assert events.index("refresh_stats") < events.index("grant_equipment")
        assert events.index("grant_equipment") < events.index("commit")
        assert events.count("commit") == 1

    async def test_creation_purges_no_cache_for_the_brand_new_character(self, monkeypatch):
        events = []
        service, _ = make_service(monkeypatch, events)

        await service.create_character(make_create_payload(), make_user())

        assert not any(event.startswith("invalidate") for event in events)

    async def test_failure_midway_rolls_back_and_returns_nothing(self, monkeypatch):
        events = []
        service, db = make_service(monkeypatch, events)

        async def broken_refresh(character):
            raise RuntimeError("stats failed")

        service.stats_service.refresh = broken_refresh

        with pytest.raises(RuntimeError):
            await service.create_character(make_create_payload(), make_user())

        assert db.commits == 0
        assert db.rollbacks >= 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateCharacterReferenceValidation:
    async def test_missing_class_reference_raises(self, monkeypatch):
        service, db = make_service(monkeypatch, [], class_exists=False)

        with pytest.raises(ClassNotFoundException):
            await service.create_character(make_create_payload(), make_user())

        assert db.commits == 0
        assert service.repository.created == []

    async def test_missing_subclass_reference_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], subclass_exists=False)

        with pytest.raises(SubclassNotFoundException):
            await service.create_character(make_create_payload(subclass_id=9), make_user())

    async def test_missing_race_reference_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], race_exists=False)

        with pytest.raises(RaceNotFoundException):
            await service.create_character(make_create_payload(), make_user())

    async def test_subrace_of_another_race_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], subrace_exists=False)

        with pytest.raises(SubraceNotFoundException):
            await service.create_character(make_create_payload(subrace_id=9), make_user())

    async def test_subrace_without_race_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [])

        with pytest.raises(SubraceNotFoundException):
            await service.create_character(make_create_payload(race_id=None, subrace_id=9), make_user())

    async def test_missing_background_reference_raises(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], background_exists=False)

        with pytest.raises(BackgroundNotFoundException):
            await service.create_character(make_create_payload(), make_user())


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateAndDelete:
    async def test_update_applies_only_provided_fields(self, monkeypatch):
        character = make_owned_character()
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        result = await service.update_character(5, CharacterUpdate(name="NewName", armor_class=16), make_user())

        assert service.repository.last_update_fields == {"name": "NewName", "armor_class": 16}
        assert result.name == "NewName"
        assert result.armor_class == 16

    async def test_update_purges_the_cache_after_the_write(self, monkeypatch):
        events = []
        service, _ = make_service(monkeypatch, events, existing_characters={5: make_owned_character()})

        await service.update_character(5, CharacterUpdate(name="X"), make_user())

        assert events == ["lock_row", "commit", "invalidate:5"]

    async def test_update_denied_for_other_player(self, monkeypatch):
        character = make_owned_character(owner_id=7)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        with pytest.raises(CharacterAccessDeniedException):
            await service.update_character(5, CharacterUpdate(name="X"), make_user(user_id=8))

        assert service.repository.last_update_fields is None

    async def test_current_hp_patch_is_clamped_to_max_hp(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], existing_characters={5: make_owned_character(max_hp=10)})

        result = await service.update_character(5, CharacterUpdate(current_hp=99), make_user())

        assert service.repository.last_update_fields == {"current_hp": 10}
        assert result.current_hp == 10

    async def test_player_cannot_raise_inspiration(self, monkeypatch):
        character = make_owned_character(inspiration=1)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        with pytest.raises(GmOnlyFieldException):
            await service.update_character(5, CharacterUpdate(inspiration=2), make_user())

        assert service.repository.last_update_fields is None

    async def test_player_can_spend_inspiration_down_or_keep_it(self, monkeypatch):
        character = make_owned_character(inspiration=3)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        await service.update_character(5, CharacterUpdate(inspiration=2), make_user())
        await service.update_character(5, CharacterUpdate(inspiration=2), make_user())

        assert character.inspiration == 2

    async def test_gm_can_raise_inspiration_on_any_character(self, monkeypatch):
        character = make_owned_character(inspiration=0)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        result = await service.update_character(5, CharacterUpdate(inspiration=4), make_user(99, UserRole.GM))

        assert result.inspiration == 4

    async def test_delete_owner_returns_true_removes_row_and_purges_cache(self, monkeypatch):
        events = []
        character = make_owned_character(owner_id=7)
        service, _ = make_service(monkeypatch, events, existing_characters={5: character})

        assert await service.delete_character(5, make_user()) is True

        assert service.repository.deleted == [character]
        assert events == ["commit", "invalidate:5"]

    async def test_delete_denied_for_other_player(self, monkeypatch):
        character = make_owned_character(owner_id=7)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        with pytest.raises(CharacterAccessDeniedException):
            await service.delete_character(5, make_user(user_id=8))

        assert service.repository.deleted == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateHp:
    async def test_damage_locks_the_row_and_commits_once_before_purging(self, monkeypatch):
        events = []
        character = make_owned_character(current_hp=10, max_hp=10)
        service, db = make_service(monkeypatch, events, existing_characters={5: character})

        result = await service.update_hp(5, HpUpdate(delta=-4), make_user())

        assert result.current_hp == 6
        assert service.repository.hp_updates == [(6, 0)]
        assert events == ["lock_row", "commit", "invalidate:5"]
        assert db.commits == 1

    async def test_damage_drains_temp_hp_first(self, monkeypatch):
        character = make_owned_character(current_hp=10, max_hp=10, temp_hp=3)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        result = await service.update_hp(5, HpUpdate(delta=-5), make_user())

        assert (result.current_hp, result.temp_hp) == (8, 0)

    async def test_healing_is_clamped_to_max_hp(self, monkeypatch):
        character = make_owned_character(current_hp=8, max_hp=10)
        service, _ = make_service(monkeypatch, [], existing_characters={5: character})

        result = await service.update_hp(5, HpUpdate(delta=50), make_user())

        assert result.current_hp == 10

    async def test_mixed_delta_and_absolute_is_rejected_without_writing(self, monkeypatch):
        events = []
        service, db = make_service(monkeypatch, events, existing_characters={5: make_owned_character()})

        with pytest.raises(InvalidHpUpdateException):
            await service.update_hp(5, HpUpdate(delta=-1, current_hp=3), make_user())

        assert service.repository.hp_updates == []
        assert db.commits == 0
        assert "invalidate:5" not in events

    async def test_empty_update_is_rejected(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], existing_characters={5: make_owned_character()})

        with pytest.raises(InvalidHpUpdateException):
            await service.update_hp(5, HpUpdate(), make_user())

    async def test_other_players_character_is_denied_before_validation(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], existing_characters={5: make_owned_character(owner_id=7)})

        with pytest.raises(CharacterAccessDeniedException):
            await service.update_hp(5, HpUpdate(), make_user(user_id=8))

    async def test_unknown_character_is_404(self, monkeypatch):
        service, _ = make_service(monkeypatch, [])

        with pytest.raises(CharacterNotFoundException):
            await service.update_hp(404, HpUpdate(delta=-1), make_user())


@pytest.mark.unit
@pytest.mark.asyncio
class TestRest:
    async def test_long_rest_restores_hp_and_resets_slots_in_one_transaction(self, monkeypatch):
        events = []
        character = make_owned_character(current_hp=2, max_hp=10, temp_hp=4)
        service, db = make_service(monkeypatch, events, existing_characters={5: character})

        result = await service.rest(5, RestRequest(type="long"), make_user())

        assert (result.current_hp, result.temp_hp) == (10, 0)
        assert service.repository.hp_updates == [(10, 0)]
        assert service.character_spell_slot_repository.resets == [5]
        assert events == ["lock_row", "commit", "invalidate:5"]
        assert db.commits == 1

    async def test_failed_slot_reset_rolls_the_hp_restore_back(self, monkeypatch):
        events = []
        character = make_owned_character(current_hp=2, max_hp=10)
        service, db = make_service(monkeypatch, events, existing_characters={5: character})
        service.character_spell_slot_repository.fail = True

        with pytest.raises(RuntimeError):
            await service.rest(5, RestRequest(type="long"), make_user())

        assert db.commits == 0
        assert db.rollbacks >= 1
        assert "invalidate:5" not in events

    async def test_short_rest_writes_nothing(self, monkeypatch):
        events = []
        character = make_owned_character(current_hp=2, max_hp=10)
        service, db = make_service(monkeypatch, events, existing_characters={5: character})

        result = await service.rest(5, RestRequest(type="short"), make_user())

        assert result.current_hp == 2
        assert service.repository.hp_updates == []
        assert db.commits == 0
        assert events == []

    async def test_rest_on_other_players_character_is_denied(self, monkeypatch):
        service, _ = make_service(monkeypatch, [], existing_characters={5: make_owned_character(owner_id=7)})

        with pytest.raises(CharacterAccessDeniedException):
            await service.rest(5, RestRequest(type="long"), make_user(user_id=8))
