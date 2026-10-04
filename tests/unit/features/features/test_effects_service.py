"""
Unit tests for FeatureEffectsService's diff engine with an in-memory repository.

Covers what the HTTP tests cannot pin down cheaply: insert/update/delete by id,
foreign ids, "nothing changed -> no character refresh", unknown catalog ids,
the choice-pick cleanup of removed options/groups, one transaction per write
and the IntegrityError mapping.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, FeatureSourceType
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.features.effects.exceptions import InvalidFeatureEffectDataError
from app.features.features.effects.schemas import ChoiceGroupsUpdate, FeatureEffectsUpdate
from app.features.features.effects.service import FeatureEffectsService
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureArmorProficiencyEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSkillProficiencyEffect,
)
from tests.unit.fakes import FakeAsyncSession


def armor_row(row_id, armor_type=ArmorProficiency.LIGHT, feature_id=1):
    row = FeatureArmorProficiencyEffect(feature_id=feature_id, armor_type=armor_type)
    row.id = row_id
    return row


def ability_row(row_id, ability=AbilityScore.STR, amount=1, feature_id=1):
    row = FeatureAbilityScoreEffect(feature_id=feature_id, ability=ability, amount=amount)
    row.id = row_id
    return row


class FakeEffectsRepository:
    """Rows live in ``rows[model]`` as ``{owner_id: {row_id: row}}``; writes are recorded."""

    def __init__(self, db, feature, rows=None, groups=None, known_ids=None):
        self.db = db
        self.feature = feature
        self.rows = rows or {}
        self.groups = groups or []
        self.known_ids = known_ids or {}
        self.added = []
        self.removed = []
        self.flushes = 0
        self.flag_refreshes = 0
        self.cleared = []
        self.for_update_calls = []
        self._next_id = 100

    async def get_plain(self, feature_id, *, for_update=False):
        self.for_update_calls.append(for_update)
        return self.feature if self.feature is not None and self.feature.id == feature_id else None

    async def load_owned_rows(self, model, owner_field, owner_ids):
        table = self.rows.get(model, {})
        return {owner_id: dict(table[owner_id]) for owner_id in owner_ids if owner_id in table}

    async def list_choice_groups(self, feature_id):
        return self.groups

    def add(self, *rows):
        for row in rows:
            if getattr(row, "id", None) is None:
                row.id = self._next_id
                self._next_id += 1
            self.added.append(row)

    async def remove(self, rows):
        self.removed.extend(rows)

    async def flush(self):
        self.flushes += 1

    async def clear_character_picks(self, *, option_ids=(), group_ids=()):
        self.cleared.append((list(option_ids), list(group_ids)))

    async def missing_ids(self, model, ids):
        known = self.known_ids.get(model.__name__, set())
        return sorted(set(ids) - known)

    async def refresh_effect_flags(self, feature):
        self.flag_refreshes += 1

    async def get_with_effect_ids(self, feature_id):
        return SimpleNamespace(id=feature_id, choice_groups=[], static_groups=[])

    async def get_choice_group_tree(self, feature_id):
        return []


@pytest.fixture
def spies(monkeypatch):
    refresh = AsyncMock()
    invalidate = AsyncMock()
    monkeypatch.setattr("app.features.features.effects.service.refresh_feature_effect_caches", refresh)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", invalidate)
    return SimpleNamespace(refresh=refresh, invalidate=invalidate)


def make_service(rows=None, groups=None, known_ids=None, feature="default"):
    db = FakeAsyncSession()
    feature = SimpleNamespace(id=1, source_type=FeatureSourceType.OTHER) if feature == "default" else feature
    service = FeatureEffectsService(db)
    service.repository = FakeEffectsRepository(db, feature, rows=rows, groups=groups, known_ids=known_ids)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestFixedEffectsDiff:
    async def test_item_without_id_is_inserted(self, spies):
        service, db = make_service()

        await service.set_fixed_effects(
            1, FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}])
        )

        assert [type(row) for row in service.repository.added] == [FeatureArmorProficiencyEffect]
        assert service.repository.added[0].feature_id == 1
        assert db.commits == 1

    async def test_item_with_id_updates_the_row_in_place(self, spies):
        row = armor_row(7)
        service, _ = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: row}}})

        await service.set_fixed_effects(
            1,
            FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"id": 7, "armor_type": "HEAVY"}]}]),
        )

        assert row.armor_type == ArmorProficiency.HEAVY
        assert service.repository.added == []
        assert service.repository.removed == []

    async def test_row_missing_from_the_payload_is_removed(self, spies):
        keep, drop = armor_row(7), armor_row(8, ArmorProficiency.SHIELD)
        service, _ = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: keep, 8: drop}}})

        await service.set_fixed_effects(
            1,
            FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"id": 7, "armor_type": "LIGHT"}]}]),
        )

        assert service.repository.removed == [drop]

    async def test_empty_list_clears_the_type(self, spies):
        rows = {FeatureArmorProficiencyEffect: {1: {7: armor_row(7)}}}
        service, _ = make_service(rows=rows)

        await service.set_fixed_effects(1, FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": []}]))

        assert len(service.repository.removed) == 1

    async def test_omitted_types_are_not_even_queried(self, spies):
        rows = {FeatureAbilityScoreEffect: {1: {3: ability_row(3)}}}
        service, _ = make_service(rows=rows)

        await service.set_fixed_effects(
            1, FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}])
        )

        assert service.repository.removed == []

    async def test_foreign_id_is_rejected_and_nothing_is_committed(self, spies):
        service, db = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: armor_row(7)}}})

        with pytest.raises(InvalidFeatureEffectDataError):
            await service.set_fixed_effects(
                1,
                FeatureEffectsUpdate(
                    static_groups=[{"effect_type": "armor", "items": [{"id": 999, "armor_type": "LIGHT"}]}]
                ),
            )

        assert db.commits == 0
        assert db.rollbacks == 1
        spies.refresh.assert_not_awaited()

    async def test_a_change_refreshes_flags_and_characters_then_purges_after_the_commit(self, spies):
        service, db = make_service()
        seen = []
        spies.refresh.side_effect = lambda *args: seen.append(("refresh", db.commits))
        spies.invalidate.side_effect = lambda namespace: seen.append(("purge", db.commits))

        await service.set_fixed_effects(
            1, FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}])
        )

        assert service.repository.flag_refreshes == 1
        assert seen[0] == ("refresh", 0)
        assert seen[1:] and all(entry == ("purge", 1) for entry in seen[1:])

    async def test_an_unchanged_payload_skips_the_character_refresh_and_the_purge(self, spies):
        row = armor_row(7)
        service, db = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: row}}})

        await service.set_fixed_effects(
            1,
            FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": [{"id": 7, "armor_type": "LIGHT"}]}]),
        )

        spies.refresh.assert_not_awaited()
        spies.invalidate.assert_not_awaited()
        assert service.repository.flag_refreshes == 0

    async def test_empty_payload_is_a_no_op(self, spies):
        service, db = make_service()

        await service.set_fixed_effects(1, FeatureEffectsUpdate())

        assert db.commits == 0
        spies.refresh.assert_not_awaited()

    async def test_write_takes_a_row_lock(self, spies):
        service, _ = make_service()

        await service.set_fixed_effects(1, FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": []}]))

        assert service.repository.for_update_calls == [True]

    async def test_unknown_skill_id_is_rejected_before_any_write(self, spies):
        service, db = make_service(known_ids={"Skill": {1}})

        with pytest.raises(InvalidFeatureEffectDataError, match=r"Unknown skill_id\(s\): \[9\]"):
            await service.set_fixed_effects(
                1,
                FeatureEffectsUpdate(
                    static_groups=[{"effect_type": "skill", "items": [{"skill_id": 1}, {"skill_id": 9}]}]
                ),
            )

        assert service.repository.added == []
        assert db.commits == 0

    async def test_unknown_feature_is_404(self, spies):
        service, _ = make_service(feature=None)

        with pytest.raises(RecordNotFoundError):
            await service.set_fixed_effects(
                1, FeatureEffectsUpdate(static_groups=[{"effect_type": "armor", "items": []}])
            )


def group_row(group_id, options=(), pick_count=1, sort_order=0, choice_type=ChoiceType.SKILL):
    group = FeatureChoiceGroup(feature_id=1, pick_count=pick_count, sort_order=sort_order, choice_type=choice_type)
    group.id = group_id
    # ``group.options`` is read by the service for an existing group
    group.options = list(options)
    return group


def option_row(option_id, group_id=1, sort_order=0):
    option = FeatureChoiceOption(group_id=group_id, sort_order=sort_order)
    option.id = option_id
    return option


@pytest.mark.unit
@pytest.mark.asyncio
class TestChoiceGroupsDiff:
    async def test_new_group_with_options_inserts_rows_and_flushes_in_two_batches(self, spies):
        service, db = make_service(known_ids={"Skill": {1, 2}})
        payload = ChoiceGroupsUpdate(
            choice_groups=[
                {
                    "choice_type": "SKILL",
                    "options": [
                        {"effects": [{"effect_type": "skill", "items": [{"skill_id": 1}]}]},
                        {"effects": [{"effect_type": "skill", "items": [{"skill_id": 2}]}]},
                    ],
                }
            ]
        )

        await service.set_choice_groups(1, payload)

        kinds = [type(row) for row in service.repository.added]
        assert kinds.count(FeatureChoiceGroup) == 1
        assert kinds.count(FeatureChoiceOption) == 2
        assert kinds.count(FeatureSkillProficiencyEffect) == 2
        # groups, then options, then the final flush before the character refresh
        assert service.repository.flushes == 3
        assert db.commits == 1

    async def test_removed_option_clears_character_picks_first(self, spies):
        keep, drop = option_row(10), option_row(11)
        group = group_row(1, options=[keep, drop])
        service, _ = make_service(groups=[group])
        payload = ChoiceGroupsUpdate(choice_groups=[{"id": 1, "choice_type": "SKILL", "options": [{"id": 10}]}])

        await service.set_choice_groups(1, payload)

        assert service.repository.cleared == [([11], [])]
        assert drop in service.repository.removed
        assert keep not in service.repository.removed

    async def test_removed_group_clears_picks_of_the_whole_group(self, spies):
        group = group_row(1, options=[option_row(10)])
        service, _ = make_service(groups=[group])

        await service.set_choice_groups(1, ChoiceGroupsUpdate(choice_groups=[]))

        assert service.repository.cleared == [([], [1])]
        assert group in service.repository.removed

    async def test_foreign_group_id_is_rejected(self, spies):
        service, db = make_service(groups=[group_row(1)])

        with pytest.raises(InvalidFeatureEffectDataError, match="Choice group id 99"):
            await service.set_choice_groups(1, ChoiceGroupsUpdate(choice_groups=[{"id": 99, "choice_type": "SKILL"}]))

        assert db.commits == 0

    async def test_foreign_option_id_is_rejected(self, spies):
        service, _ = make_service(groups=[group_row(1, options=[option_row(10)])])
        payload = ChoiceGroupsUpdate(choice_groups=[{"id": 1, "choice_type": "SKILL", "options": [{"id": 77}]}])

        with pytest.raises(InvalidFeatureEffectDataError, match="Choice option id 77"):
            await service.set_choice_groups(1, payload)

    async def test_group_scalars_are_updated_in_place(self, spies):
        group = group_row(1, pick_count=1)
        service, _ = make_service(groups=[group])

        await service.set_choice_groups(
            1, ChoiceGroupsUpdate(choice_groups=[{"id": 1, "choice_type": "SKILL", "pick_count": 3, "sort_order": 2}])
        )

        assert (group.pick_count, group.sort_order) == (3, 2)

    async def test_unchanged_tree_is_a_no_op(self, spies):
        group = group_row(1, options=[option_row(10)])
        service, _ = make_service(groups=[group])

        await service.set_choice_groups(
            1, ChoiceGroupsUpdate(choice_groups=[{"id": 1, "choice_type": "SKILL", "options": [{"id": 10}]}])
        )

        spies.refresh.assert_not_awaited()
        spies.invalidate.assert_not_awaited()

    async def test_existing_options_effects_are_diffed_with_one_query_per_effect_type(self, spies):
        queried = []
        group = group_row(1, options=[option_row(10), option_row(11)])
        service, _ = make_service(groups=[group])
        original = service.repository.load_owned_rows

        async def spy(model, owner_field, owner_ids):
            queried.append((model.__name__, sorted(owner_ids)))
            return await original(model, owner_field, owner_ids)

        service.repository.load_owned_rows = spy

        await service.set_choice_groups(
            1,
            ChoiceGroupsUpdate(choice_groups=[{"id": 1, "choice_type": "SKILL", "options": [{"id": 10}, {"id": 11}]}]),
        )

        assert len(queried) == 6
        assert all(owner_ids == [10, 11] for _, owner_ids in queried)

    async def test_unknown_spell_id_inside_an_option_is_422(self, spies):
        service, db = make_service(known_ids={"Spell": set()})
        payload = ChoiceGroupsUpdate(
            choice_groups=[
                {
                    "choice_type": "SPELL",
                    "options": [{"effects": [{"effect_type": "spell", "items": [{"spell_id": 5}]}]}],
                }
            ]
        )

        with pytest.raises(InvalidFeatureEffectDataError, match=r"Unknown spell_id\(s\): \[5\]"):
            await service.set_choice_groups(1, payload)

        assert db.commits == 0


class FakeDriverError(Exception):
    """Stands in for ``IntegrityError.orig``."""


@pytest.mark.unit
@pytest.mark.asyncio
class TestIntegrityErrorMapping:
    def _failing_service(self, message):
        service, db = make_service()

        async def boom():
            raise IntegrityError("stmt", {}, FakeDriverError(message))

        service.repository.flush = boom
        return service, db

    def _payload(self):
        return ChoiceGroupsUpdate(choice_groups=[{"choice_type": "SKILL", "options": []}])

    async def test_a_restrict_violation_on_character_picks_is_a_409(self, spies):
        service, db = self._failing_service(
            'update or delete on table "feature_choice_options" violates foreign key constraint '
            '"character_feature_choices_choice_option_id_fkey" on table "character_feature_choices"'
        )

        with pytest.raises(RecordInUseError):
            await service.set_choice_groups(1, self._payload())

        assert db.rollbacks == 1

    async def test_any_other_integrity_error_is_not_disguised_as_in_use(self, spies):
        service, db = self._failing_service(
            'violates check constraint "check_feature_choice_group_pick_count_positive"'
        )

        with pytest.raises(IntegrityError):
            await service.set_choice_groups(1, self._payload())

        assert db.rollbacks == 1
