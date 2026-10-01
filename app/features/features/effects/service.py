"""Feature effects service: read and diff-write the effect engine of a feature."""

from collections.abc import Iterable
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import unit_of_work
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.characters.progression.feature_sync import refresh_feature_effect_caches
from app.features.features.cache import invalidate_feature_cache_after_commit
from app.features.features.effects.exceptions import InvalidFeatureEffectDataError
from app.features.features.effects.repository import FeatureEffectsRepository
from app.features.features.effects.schemas import (
    ChoiceGroupPayload,
    ChoiceGroupResponse,
    ChoiceGroupsUpdate,
    FeatureEffectsResponse,
    FeatureEffectsUpdate,
)
from app.models import Item, Skill, Spell
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureArmorProficiencyEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSavingThrowEffect,
    FeatureSkillProficiencyEffect,
    FeatureSpellGrantEffect,
    FeatureWeaponProficiencyEffect,
)
from app.models.features.feature_model import Feature

# (effect row model, attribute name on the payload/response schemas) per effect type.
_EFFECT_DIMENSIONS = (
    (FeatureAbilityScoreEffect, "ability_effects"),
    (FeatureSkillProficiencyEffect, "skill_effects"),
    (FeatureSavingThrowEffect, "saving_throw_effects"),
    (FeatureArmorProficiencyEffect, "armor_effects"),
    (FeatureWeaponProficiencyEffect, "weapon_effects"),
    (FeatureSpellGrantEffect, "spell_effects"),
)

# Catalog model behind each referencing effect field: (schema field, id attribute, label, model).
_CATALOG_REFERENCES = (
    ("skill_effects", "skill_id", "skill_id", Skill),
    ("weapon_effects", "item_id", "item_id", Item),
    ("spell_effects", "spell_id", "spell_id", Spell),
)


class FeatureEffectsService:
    """
    Everything about a feature's effects: its choice groups ("pick N of M",
    each option a bundle of effects) and its fixed automatic effects across
    the six typed tables.

    Writes **diff by id** against the existing rows rather than deleting
    everything and recreating it: a row whose id is given and matches an
    existing one is updated in place, a row with no id is inserted, and an
    existing row whose id is absent from the payload is deleted. This
    matters because ``CharacterFeatureChoice.choice_option_id`` is
    ``ondelete RESTRICT``: ``set_choice_groups`` deletes the stored picks of
    a removed option/group itself (the pick reverts to pending) before
    removing it. Each write is one transaction (``unit_of_work``): the diff,
    the denormalized ``has_*`` flags, the re-materialization of every
    granted character (``refresh_feature_effect_caches``) and the post-commit
    cache purge. A write that changes nothing skips the character refresh.
    """

    repository: FeatureEffectsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the service with the effect-engine repository."""

        self.repository = FeatureEffectsRepository(db)

    async def _get_feature_or_404(self, feature_id: int, *, for_update: bool = False) -> Feature:
        """The bare feature row (row-locked for writes), or ``RecordNotFoundError``."""

        feature = await self.repository.get_plain(feature_id, for_update=for_update)
        if feature is None:
            raise RecordNotFoundError(model_name="Feature", model_id=str(feature_id))

        return feature

    async def get_effects(self, feature_id: int) -> FeatureEffectsResponse:
        """Return a feature's complete effect tree: choice groups + fixed effects."""

        feature = await self.repository.get_with_effect_ids(feature_id)
        if feature is None:
            raise RecordNotFoundError(model_name="Feature", model_id=str(feature_id))

        return FeatureEffectsResponse(
            feature_id=feature.id,
            choice_groups=[ChoiceGroupResponse.model_validate(group) for group in feature.choice_groups],
            static_groups=feature.static_groups,
        )

    async def get_choice_groups(self, feature_id: int) -> list[ChoiceGroupResponse]:
        """Return a feature's choice groups with their options and bundles."""

        await self._get_feature_or_404(feature_id)
        return await self._choice_group_responses(feature_id)

    async def _choice_group_responses(self, feature_id: int) -> list[ChoiceGroupResponse]:
        groups = await self.repository.get_choice_group_tree(feature_id)
        return [ChoiceGroupResponse.model_validate(group) for group in groups]

    async def _ensure_targets_exist(self, owners: Iterable[Any]) -> None:
        """Raise ``InvalidFeatureEffectDataError`` (422) for any skill/item/spell id the payloads reference but the catalog lacks."""

        owners = list(owners)
        for field_name, id_attr, label, model in _CATALOG_REFERENCES:
            wanted = {
                getattr(effect, id_attr)
                for owner in owners
                for effect in getattr(owner, field_name) or []
                if getattr(effect, id_attr) is not None
            }
            missing = await self.repository.missing_ids(model, wanted)
            if missing:
                raise InvalidFeatureEffectDataError(f"Unknown {label}(s): {missing}.")

    async def _apply_rows_diff(
        self, model: Any, owner_field: str, owner_id: int, payload_items: list, existing_by_id: dict[int, Any]
    ) -> bool:
        """
        Apply the insert/update/delete diff of ``payload_items`` against
        ``existing_by_id`` (the owner's current rows); True when anything changed.

        An item whose id matches none of the existing rows (stale or foreign
        id) raises ``InvalidFeatureEffectDataError`` rather than silently
        creating a duplicate.
        """

        changed = False
        seen_ids: set[int] = set()

        for item in payload_items:
            values = item.model_dump(exclude={"id"})

            if item.id is None:
                self.repository.add(model(**{owner_field: owner_id}, **values))
                changed = True
                continue

            row = existing_by_id.get(item.id)
            if row is None:
                raise InvalidFeatureEffectDataError(
                    f"{model.__name__} id {item.id} does not belong to this feature/option."
                )

            for field, value in values.items():
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed = True
            seen_ids.add(item.id)

        removed = [row for row_id, row in existing_by_id.items() if row_id not in seen_ids]
        if removed:
            await self.repository.remove(removed)
            changed = True

        return changed

    async def set_fixed_effects(self, feature_id: int, data: FeatureEffectsUpdate) -> FeatureEffectsResponse:
        """
        Diff a feature's fixed effects against the payload.

        Only the effect types present in the payload are touched (``[]``
        clears a type); choice groups are untouched. When something changed,
        every character granted the feature is re-materialized in the same
        transaction.
        """

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        await self._ensure_targets_exist([data])

        provided = [
            (model, field_name) for model, field_name in _EFFECT_DIMENSIONS if getattr(data, field_name) is not None
        ]
        if not provided:
            return await self.get_effects(feature_id)

        db = self.repository.db
        async with unit_of_work(db):
            changed = False
            for model, field_name in provided:
                existing = (await self.repository.load_owned_rows(model, "feature_id", [feature.id])).get(
                    feature.id, {}
                )
                changed |= await self._apply_rows_diff(
                    model, "feature_id", feature.id, getattr(data, field_name), existing
                )

            if changed:
                await self._finish_write(feature)

        return await self.get_effects(feature_id)

    async def _finish_write(self, feature: Feature) -> None:
        """Flush the diff, refresh the ``has_*`` flags and every granted character, schedule the cache purge."""

        await self.repository.flush()
        await self.repository.refresh_effect_flags(feature)
        await refresh_feature_effect_caches(self.repository.db, feature.id)
        await invalidate_feature_cache_after_commit(self.repository.db, feature.source_type)

    async def set_choice_groups(self, feature_id: int, data: ChoiceGroupsUpdate) -> list[ChoiceGroupResponse]:
        """
        Diff a feature's choice groups (and their options/effects) against
        the payload — see the class docstring. Dropping an option or a whole
        group that a character already picked clears that character's
        stored pick (reverting it to pending) instead of failing; every
        character currently granted the feature is then re-materialized.
        """

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        await self._ensure_targets_exist(option for group in data.choice_groups for option in group.options)

        async with unit_of_work(self.repository.db):
            try:
                changed = await self._diff_choice_groups(feature, data.choice_groups)
                if changed:
                    await self._finish_write(feature)
            except IntegrityError as exc:
                if "character_feature_choices" not in str(exc.orig):
                    raise
                raise RecordInUseError(
                    model_name="FeatureChoiceOption",
                    model_id="one or more removed options/groups",
                    reason="still referenced by a character's answered choice",
                ) from exc

        return await self._choice_group_responses(feature_id)

    async def _diff_choice_groups(self, feature: Feature, payloads: list[ChoiceGroupPayload]) -> bool:
        """
        Diff the groups, their options and every option's effect rows; True when anything changed.

        Rows are inserted in two flushes (new groups, then new options) and
        the existing options' effect rows are loaded with one query per
        effect type across ALL groups. A removed option/group first loses
        every character's stored pick of it, so the pick reverts to pending.
        """

        repo = self.repository
        existing_groups = {group.id: group for group in await repo.list_choice_groups(feature.id)}

        changed = False
        seen_group_ids: set[int] = set()
        plan: list[tuple[FeatureChoiceGroup, ChoiceGroupPayload]] = []
        new_groups: list[FeatureChoiceGroup] = []

        for payload in payloads:
            if payload.id is None:
                group = FeatureChoiceGroup(
                    feature_id=feature.id,
                    pick_count=payload.pick_count,
                    sort_order=payload.sort_order,
                    choice_type=payload.choice_type,
                )
                new_groups.append(group)
            else:
                group = existing_groups.get(payload.id)
                if group is None:
                    raise InvalidFeatureEffectDataError(
                        f"Choice group id {payload.id} does not belong to this feature."
                    )
                seen_group_ids.add(payload.id)
                for field in ("pick_count", "sort_order", "choice_type"):
                    if getattr(group, field) != getattr(payload, field):
                        setattr(group, field, getattr(payload, field))
                        changed = True
            plan.append((group, payload))

        if new_groups:
            repo.add(*new_groups)
            await repo.flush()
            changed = True

        kept_options: list[tuple[FeatureChoiceOption, Any]] = []
        new_options: list[tuple[FeatureChoiceOption, Any]] = []
        removed_options: list[FeatureChoiceOption] = []

        for group, payload in plan:
            existing_options = {} if group in new_groups else {option.id: option for option in group.options}
            seen_option_ids: set[int] = set()

            for option_payload in payload.options:
                if option_payload.id is None:
                    option = FeatureChoiceOption(group_id=group.id, sort_order=option_payload.sort_order)
                    new_options.append((option, option_payload))
                    continue

                option = existing_options.get(option_payload.id)
                if option is None:
                    raise InvalidFeatureEffectDataError(
                        f"Choice option id {option_payload.id} does not belong to group {group.id}."
                    )
                if option.sort_order != option_payload.sort_order:
                    option.sort_order = option_payload.sort_order
                    changed = True
                seen_option_ids.add(option.id)
                kept_options.append((option, option_payload))

            removed_options.extend(
                option for option_id, option in existing_options.items() if option_id not in seen_option_ids
            )

        if new_options:
            repo.add(*(option for option, _ in new_options))
            await repo.flush()
            changed = True

        for model, field_name in _EFFECT_DIMENSIONS:
            existing_by_option = await repo.load_owned_rows(
                model, "choice_option_id", [option.id for option, _ in kept_options]
            )
            for option, option_payload in kept_options:
                changed |= await self._apply_rows_diff(
                    model,
                    "choice_option_id",
                    option.id,
                    getattr(option_payload, field_name),
                    existing_by_option.get(option.id, {}),
                )
            for option, option_payload in new_options:
                await self._apply_rows_diff(
                    model, "choice_option_id", option.id, getattr(option_payload, field_name), {}
                )

        removed_groups = [group for group_id, group in existing_groups.items() if group_id not in seen_group_ids]
        if removed_options or removed_groups:
            await repo.clear_character_picks(
                option_ids=[option.id for option in removed_options], group_ids=[group.id for group in removed_groups]
            )
            await repo.remove(removed_options)
            await repo.remove(removed_groups)
            changed = True

        return changed
