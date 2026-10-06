"""
Unit tests for FeatureEffectsService's point writes with an in-memory repository.

Covers what the HTTP tests cannot pin down cheaply: ids rejected on create, merge-and-validate on
update, rows not owned by the feature/option, the effect-type-vs-choice-type rule, the choice-pick
cleanup of removed options/groups, insert order of a new group, "nothing changed -> no write",
one transaction per write and the IntegrityError mapping.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, FeatureSourceType
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.features.effects.exceptions import InvalidFeatureEffectDataError
from app.features.features.effects.schemas import (
    ChoiceGroupPatch,
    ChoiceGroupPayload,
    ChoiceOptionPatch,
    ChoiceOptionPayload,
    FeatureEffectsUpdate,
)
from app.features.features.effects.service import FeatureEffectsService
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureArmorProficiencyEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSkillProficiencyEffect,
    FeatureWeaponProficiencyEffect,
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


def weapon_item_row(row_id, item_id=2, feature_id=1):
    row = FeatureWeaponProficiencyEffect(feature_id=feature_id, weapon_category=None, item_id=item_id)
    row.id = row_id
    return row


def group_row(group_id, options=(), pick_count=1, sort_order=0, choice_type=ChoiceType.SKILL):
    group = FeatureChoiceGroup(feature_id=1, pick_count=pick_count, sort_order=sort_order, choice_type=choice_type)
    group.id = group_id
    group.options = list(options)
    return group


def option_row(option_id, group_id=1, sort_order=0):
    option = FeatureChoiceOption(group_id=group_id, sort_order=sort_order)
    option.id = option_id
    return option


def armor_groups(*armor_types):
    return [{"effect_type": "armor", "items": [{"armor_type": armor_type} for armor_type in armor_types]}]


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
class TestAddFixedEffects:
    async def test_items_become_new_rows_owned_by_the_feature(self, spies):
        service, db = make_service()

        await service.add_fixed_effects(1, FeatureEffectsUpdate(static_groups=armor_groups("LIGHT", "HEAVY")))

        assert [type(row) for row in service.repository.added] == [FeatureArmorProficiencyEffect] * 2
        assert {row.feature_id for row in service.repository.added} == {1}
        assert db.commits == 1

    async def test_an_item_carrying_an_id_is_rejected(self, spies):
        service, db = make_service()
        data = FeatureEffectsUpdate(
            static_groups=[{"effect_type": "armor", "items": [{"id": 7, "armor_type": "LIGHT"}]}]
        )

        with pytest.raises(InvalidFeatureEffectDataError, match="must not carry an id"):
            await service.add_fixed_effects(1, data)

        assert service.repository.added == []
        assert db.commits == 0

    async def test_an_empty_payload_is_a_no_op(self, spies):
        service, db = make_service()

        await service.add_fixed_effects(1, FeatureEffectsUpdate())

        assert db.commits == 0
        assert service.repository.flag_refreshes == 0
        spies.refresh.assert_not_awaited()
        spies.invalidate.assert_not_awaited()

    async def test_unknown_skill_id_is_rejected_before_any_write(self, spies):
        service, db = make_service(known_ids={"Skill": {1}})
        data = FeatureEffectsUpdate(
            static_groups=[{"effect_type": "skill", "items": [{"skill_id": 1}, {"skill_id": 9}]}]
        )

        with pytest.raises(InvalidFeatureEffectDataError, match=r"Unknown skill_id\(s\): \[9\]"):
            await service.add_fixed_effects(1, data)

        assert service.repository.added == []
        assert db.commits == 0

    async def test_write_takes_a_row_lock(self, spies):
        service, _ = make_service()

        await service.add_fixed_effects(1, FeatureEffectsUpdate(static_groups=armor_groups("LIGHT")))

        assert service.repository.for_update_calls == [True]

    async def test_unknown_feature_is_404(self, spies):
        service, _ = make_service(feature=None)

        with pytest.raises(RecordNotFoundError):
            await service.add_fixed_effects(1, FeatureEffectsUpdate(static_groups=armor_groups("LIGHT")))

    async def test_a_change_refreshes_flags_and_characters_then_purges_after_the_commit(self, spies):
        service, db = make_service()
        seen = []
        spies.refresh.side_effect = lambda *args: seen.append(("refresh", db.commits))
        spies.invalidate.side_effect = lambda namespace: seen.append(("purge", db.commits))

        await service.add_fixed_effects(1, FeatureEffectsUpdate(static_groups=armor_groups("LIGHT")))

        assert service.repository.flag_refreshes == 1
        assert seen[0] == ("refresh", 0)
        assert seen[1:] and all(entry == ("purge", 1) for entry in seen[1:])


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateFixedEffect:
    async def test_changes_are_merged_over_the_current_values(self, spies):
        row = ability_row(3, AbilityScore.STR, amount=1)
        service, db = make_service(rows={FeatureAbilityScoreEffect: {1: {3: row}}})

        await service.update_fixed_effect(1, "ability", 3, {"amount": 2})

        assert (row.ability, row.amount) == (AbilityScore.STR, 2)
        assert db.commits == 1
        assert service.repository.added == []

    async def test_row_not_owned_by_the_feature_is_404(self, spies):
        service, db = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: armor_row(7)}}})

        with pytest.raises(RecordNotFoundError):
            await service.update_fixed_effect(1, "armor", 999, {"armor_type": "HEAVY"})

        assert db.commits == 0

    async def test_the_merged_item_is_validated_as_a_whole(self, spies):
        row = weapon_item_row(5, item_id=2)
        service, db = make_service(rows={FeatureWeaponProficiencyEffect: {1: {5: row}}}, known_ids={"Item": {2}})

        with pytest.raises(InvalidFeatureEffectDataError, match="exactly one"):
            await service.update_fixed_effect(1, "weapon", 5, {"weapon_category": "MARTIAL"})

        assert row.weapon_category is None
        assert db.commits == 0

    async def test_unknown_catalog_id_in_the_changes_is_rejected(self, spies):
        row = FeatureSkillProficiencyEffect(feature_id=1, skill_id=1, grants_expertise=False)
        row.id = 4
        service, db = make_service(rows={FeatureSkillProficiencyEffect: {1: {4: row}}}, known_ids={"Skill": {1}})

        with pytest.raises(InvalidFeatureEffectDataError, match=r"Unknown skill_id\(s\): \[9\]"):
            await service.update_fixed_effect(1, "skill", 4, {"skill_id": 9})

        assert row.skill_id == 1
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveFixedEffect:
    async def test_the_row_is_deleted_and_characters_refreshed(self, spies):
        row = armor_row(7)
        service, db = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: row}}})

        await service.remove_fixed_effect(1, "armor", 7)

        assert service.repository.removed == [row]
        assert service.repository.flag_refreshes == 1
        spies.refresh.assert_awaited_once()
        assert db.commits == 1

    async def test_row_not_owned_by_the_feature_is_404(self, spies):
        service, db = make_service(rows={FeatureArmorProficiencyEffect: {1: {7: armor_row(7)}}})

        with pytest.raises(RecordNotFoundError):
            await service.remove_fixed_effect(1, "armor", 8)

        assert service.repository.removed == []
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestChoiceGroups:
    async def test_new_group_inserts_group_then_options_then_effect_rows(self, spies):
        service, db = make_service(known_ids={"Skill": {1, 2}})
        payload = ChoiceGroupPayload(
            choice_type="SKILL",
            pick_count=1,
            options=[
                {"effects": [{"effect_type": "skill", "items": [{"skill_id": 1}]}]},
                {"effects": [{"effect_type": "skill", "items": [{"skill_id": 2}]}]},
            ],
        )

        await service.add_choice_group(1, payload)

        added = service.repository.added
        assert [type(row) for row in added] == [FeatureChoiceGroup] + [FeatureChoiceOption] * 2 + [
            FeatureSkillProficiencyEffect
        ] * 2
        group, first_option, second_option, first_effect, second_effect = added
        assert group.feature_id == 1
        assert first_option.group_id == group.id
        assert (first_effect.choice_option_id, second_effect.choice_option_id) == (first_option.id, second_option.id)
        # group, options, then the final flush before the character refresh
        assert service.repository.flushes == 3
        assert db.commits == 1

    async def test_ids_in_a_new_group_are_rejected(self, spies):
        service, db = make_service()

        with pytest.raises(InvalidFeatureEffectDataError, match="must not carry an id"):
            await service.add_choice_group(1, ChoiceGroupPayload(id=5, choice_type="SKILL"))
        with pytest.raises(InvalidFeatureEffectDataError, match="must not carry an id"):
            await service.add_choice_group(1, ChoiceGroupPayload(choice_type="SKILL", options=[{"id": 3}]))

        assert service.repository.added == []
        assert db.commits == 0

    async def test_unknown_spell_id_inside_an_option_is_422(self, spies):
        service, db = make_service(known_ids={"Spell": set()})
        payload = ChoiceGroupPayload(
            choice_type="SPELL",
            options=[{"effects": [{"effect_type": "spell", "items": [{"spell_id": 5}]}]}],
        )

        with pytest.raises(InvalidFeatureEffectDataError, match=r"Unknown spell_id\(s\): \[5\]"):
            await service.add_choice_group(1, payload)

        assert service.repository.added == []
        assert db.commits == 0

    async def test_update_changes_only_the_sent_fields(self, spies):
        group = group_row(1, pick_count=1, sort_order=4)
        service, db = make_service(groups=[group])

        await service.update_choice_group(1, 1, ChoiceGroupPatch(pick_count=3))

        assert (group.pick_count, group.sort_order) == (3, 4)
        assert db.commits == 1

    async def test_update_with_nothing_sent_writes_and_refreshes_nothing(self, spies):
        service, db = make_service(groups=[group_row(1)])

        await service.update_choice_group(1, 1, ChoiceGroupPatch())

        assert db.commits == 0
        assert service.repository.flushes == 0
        spies.refresh.assert_not_awaited()
        spies.invalidate.assert_not_awaited()

    async def test_unknown_group_is_404(self, spies):
        service, _ = make_service(groups=[group_row(1)])

        with pytest.raises(RecordNotFoundError):
            await service.update_choice_group(1, 99, ChoiceGroupPatch(pick_count=2))
        with pytest.raises(RecordNotFoundError):
            await service.remove_choice_group(1, 99)

    async def test_remove_clears_the_picks_of_the_whole_group_first(self, spies):
        group = group_row(1, options=[option_row(10), option_row(11)])
        service, db = make_service(groups=[group])

        await service.remove_choice_group(1, 1)

        assert service.repository.cleared == [([10, 11], [1])]
        assert service.repository.removed == [group]
        assert db.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestChoiceOptions:
    async def test_add_inserts_the_option_then_its_effect_rows(self, spies):
        service, db = make_service(groups=[group_row(1)], known_ids={"Skill": {1}})
        payload = ChoiceOptionPayload(sort_order=2, effects=[{"effect_type": "skill", "items": [{"skill_id": 1}]}])

        await service.add_choice_option(1, 1, payload)

        option, effect = service.repository.added
        assert (type(option), option.group_id, option.sort_order) == (FeatureChoiceOption, 1, 2)
        assert (type(effect), effect.choice_option_id) == (FeatureSkillProficiencyEffect, option.id)
        assert db.commits == 1

    async def test_add_rejects_an_id_and_an_effect_type_the_group_does_not_allow(self, spies):
        service, db = make_service(groups=[group_row(1, choice_type=ChoiceType.SKILL)])

        with pytest.raises(InvalidFeatureEffectDataError, match="must not carry an id"):
            await service.add_choice_option(1, 1, ChoiceOptionPayload(id=4))
        with pytest.raises(InvalidFeatureEffectDataError, match="may only carry 'skill' effects"):
            await service.add_choice_option(1, 1, ChoiceOptionPayload(effects=armor_groups("LIGHT")))

        assert service.repository.added == []
        assert db.commits == 0

    async def test_update_sets_the_sort_order(self, spies):
        option = option_row(10, sort_order=0)
        service, db = make_service(groups=[group_row(1, options=[option])])

        await service.update_choice_option(1, 1, 10, ChoiceOptionPatch(sort_order=5))

        assert option.sort_order == 5
        assert db.commits == 1

    async def test_option_of_another_group_is_404(self, spies):
        service, _ = make_service(groups=[group_row(1, options=[option_row(10)]), group_row(2)])

        with pytest.raises(RecordNotFoundError):
            await service.update_choice_option(1, 2, 10, ChoiceOptionPatch(sort_order=1))
        with pytest.raises(RecordNotFoundError):
            await service.remove_choice_option(1, 2, 10)

    async def test_remove_clears_only_that_options_picks_first(self, spies):
        keep, drop = option_row(10), option_row(11)
        service, db = make_service(groups=[group_row(1, options=[keep, drop])])

        await service.remove_choice_option(1, 1, 11)

        assert service.repository.cleared == [([11], [])]
        assert service.repository.removed == [drop]
        assert db.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestOptionEffects:
    async def test_add_rejects_an_effect_type_the_group_does_not_allow(self, spies):
        service, db = make_service(groups=[group_row(1, options=[option_row(10)], choice_type=ChoiceType.SKILL)])

        with pytest.raises(InvalidFeatureEffectDataError, match="may only carry 'skill' effects"):
            await service.add_option_effects(1, 1, 10, FeatureEffectsUpdate(static_groups=armor_groups("LIGHT")))

        assert service.repository.added == []
        assert db.commits == 0

    async def test_add_inserts_rows_owned_by_the_option(self, spies):
        service, db = make_service(groups=[group_row(1, options=[option_row(10)])], known_ids={"Skill": {3}})
        data = FeatureEffectsUpdate(static_groups=[{"effect_type": "skill", "items": [{"skill_id": 3}]}])

        await service.add_option_effects(1, 1, 10, data)

        (effect,) = service.repository.added
        assert (type(effect), effect.choice_option_id, effect.skill_id) == (FeatureSkillProficiencyEffect, 10, 3)
        assert db.commits == 1

    async def test_update_and_remove_only_see_the_options_own_rows(self, spies):
        row = armor_row(7)
        service, db = make_service(
            groups=[group_row(1, options=[option_row(10)], choice_type=ChoiceType.ARMOR)],
            rows={FeatureArmorProficiencyEffect: {10: {7: row}}},
        )

        await service.update_option_effect(1, 1, 10, "armor", 7, {"armor_type": "HEAVY"})
        assert row.armor_type == ArmorProficiency.HEAVY

        with pytest.raises(RecordNotFoundError):
            await service.update_option_effect(1, 1, 10, "armor", 8, {"armor_type": "HEAVY"})
        with pytest.raises(RecordNotFoundError):
            await service.remove_option_effect(1, 1, 10, "armor", 8)

        await service.remove_option_effect(1, 1, 10, "armor", 7)
        assert service.repository.removed == [row]
        assert db.commits == 2


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
        return ChoiceGroupPayload(choice_type="SKILL")

    async def test_a_restrict_violation_on_character_picks_is_a_409(self, spies):
        service, db = self._failing_service(
            'update or delete on table "feature_choice_options" violates foreign key constraint '
            '"character_feature_choices_choice_option_id_fkey" on table "character_feature_choices"'
        )

        with pytest.raises(RecordInUseError):
            await service.add_choice_group(1, self._payload())

        assert db.rollbacks == 1

    async def test_any_other_integrity_error_is_not_disguised_as_in_use(self, spies):
        service, db = self._failing_service(
            'violates check constraint "check_feature_choice_group_pick_count_positive"'
        )

        with pytest.raises(IntegrityError):
            await service.add_choice_group(1, self._payload())

        assert db.rollbacks == 1
