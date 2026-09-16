"""Feature effects service: read/write the effect engine on the reference side (Phase 3)."""

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.service import BaseService
from app.core.exceptions import RecordInUseError
from app.features.characters.progression.feature_sync import refresh_feature_effect_caches
from app.features.features.cache import FEATURE_CACHE_NAMESPACES, purge_feature_cache_for_source
from app.features.features.crud.repository import FeatureRepository
from app.features.features.crud.schemas import FeatureResponse
from app.features.features.effects.exceptions import InvalidFeatureEffectDataError
from app.features.features.effects.schemas import (
    AbilityEffectItem,
    ArmorEffectItem,
    ChoiceGroupResponse,
    ChoiceGroupsUpdate,
    ChoiceOptionPayload,
    ChoiceOptionResponse,
    FeatureEffectsResponse,
    FeatureEffectsUpdate,
    SavingThrowEffectItem,
    SkillEffectItem,
    SpellEffectItem,
    WeaponEffectItem,
)
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
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


# Model -> payload-item conversion tables (kept close to the service so both
# directions read the same field names).
def _to_choice_group_response(group: FeatureChoiceGroup) -> ChoiceGroupResponse:
    """Convert a choice group (with eager-loaded options/effects) to its response schema."""

    option_responses: list[ChoiceOptionResponse] = []
    for option in group.options:
        option_responses.append(
            ChoiceOptionResponse(
                id=option.id,
                sort_order=option.sort_order,
                ability_effects=[AbilityEffectItem.model_validate(e) for e in option.ability_effects],
                skill_effects=[SkillEffectItem.model_validate(e) for e in option.skill_effects],
                saving_throw_effects=[SavingThrowEffectItem.model_validate(e) for e in option.saving_throw_effects],
                armor_effects=[ArmorEffectItem.model_validate(e) for e in option.armor_effects],
                weapon_effects=[WeaponEffectItem.model_validate(e) for e in option.weapon_effects],
                spell_effects=[SpellEffectItem.model_validate(e) for e in option.spell_effects],
            )
        )
    return ChoiceGroupResponse(
        id=group.id,
        feature_id=group.feature_id,
        pick_count=group.pick_count,
        sort_order=group.sort_order,
        choice_type=group.choice_type,
        options=option_responses,
    )


class FeatureEffectsService(BaseService[Feature, None, None, FeatureResponse, None]):
    """
    Everything about a feature's effects: its choice groups ("pick N of M",
    each option a bundle of effects) and its fixed automatic effects across
    the six typed tables.

    Writes **diff by id** against the existing rows (``_diff_owned_rows`` /
    ``_diff_choice_options``) rather than deleting everything and
    recreating it from the payload: a row whose id is given and matches an
    existing one is updated in place, a row with no id is inserted, and an
    existing row whose id is absent from the payload is deleted. This
    matters because ``CharacterFeatureChoice.choice_option_id`` is
    ``ondelete RESTRICT`` — dropping an option (or a whole group) that a
    character already picked would otherwise fail outright. Instead,
    ``set_choice_groups`` deletes that character's now-invalid
    ``CharacterFeatureChoice`` row(s) itself before removing the
    option/group, so the pick simply reverts to pending — every character
    currently granted the feature is then re-materialized (and their
    ability totals recomputed) by the same ``refresh_feature_effect_caches``
    call every write already does, so the option's effects disappear from
    everyone it affected, not just the one whose pick was cleared. The
    ``IntegrityError`` → ``RecordInUseError`` (409) catch around the final
    flush/commit is a safety net for anything this proactive cleanup missed,
    not the primary mechanism. Everything runs inside the caller's
    transaction and purges the ``features`` cache. Because an effect edit
    can change what granted characters receive, every write also
    re-materializes the granted characters' effect rows via
    ``refresh_feature_effect_caches`` → ``reconcile_effect_rows_for_feature``
    (the known one-way characters import — no import cycle).
    """

    repository: FeatureRepository

    cache_namespaces = FEATURE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the feature repository."""

        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
        )

    async def _feature_with_effects(self, feature_id: int) -> Feature:
        """Fetch the feature with its whole engine effect tree eagerly loaded."""

        feature = await self._get_or_404(feature_id)
        return await self.repository.get_with_effects(feature_id, fallback=feature)

    async def get_effects(self, feature_id: int) -> FeatureEffectsResponse:
        """Return a feature's complete effect tree: choice groups + fixed effects."""

        feature = await self._feature_with_effects(feature_id)

        return FeatureEffectsResponse(
            feature_id=feature.id,
            choice_groups=[_to_choice_group_response(group) for group in feature.choice_groups],
            static_groups=feature.static_groups,
        )

    async def _diff_owned_rows(self, model, owner_field: str, owner_id: int, payload_items: list) -> None:
        """
        Diff ``payload_items`` (each optionally carrying its DB ``id``)
        against ``model``'s existing rows where ``owner_field == owner_id``.

        An item with an id matching an existing row updates that row in
        place; an item with no id inserts a new row; an existing row whose
        id is absent from ``payload_items`` is deleted. An item whose id
        matches nothing raises ``InvalidFeatureEffectDataError`` (stale or
        foreign id) rather than silently creating a duplicate.
        """

        db = self.repository.db
        owner_col = getattr(model, owner_field)
        existing = (await db.execute(select(model).where(owner_col == owner_id))).scalars().all()
        existing_by_id = {row.id: row for row in existing}

        await self._apply_owned_rows_diff(model, owner_field, owner_id, payload_items, existing_by_id)

    async def _load_owned_rows_by_owner(self, model, owner_field: str, owner_ids: set[int]) -> dict[int, dict]:
        """
        One batched query for ``model`` rows across every id in ``owner_ids``,
        grouped by owner id — the multi-owner counterpart to the single-owner
        query inside ``_diff_owned_rows``, used to diff many choice options'
        effect rows without a query per option.
        """

        if not owner_ids:
            return {}

        db = self.repository.db
        owner_col = getattr(model, owner_field)
        existing = (await db.execute(select(model).where(owner_col.in_(owner_ids)))).scalars().all()

        by_owner: dict[int, dict] = {}
        for row in existing:
            by_owner.setdefault(getattr(row, owner_field), {})[row.id] = row

        return by_owner

    async def _apply_owned_rows_diff(
        self, model, owner_field: str, owner_id: int, payload_items: list, existing_by_id: dict
    ) -> None:
        """Apply the insert/update/delete diff for one owner against pre-fetched ``existing_by_id`` rows."""

        db = self.repository.db
        seen_ids: set[int] = set()

        for item in payload_items:
            dump = item.model_dump(exclude={"id"})
            if item.id is not None:
                row = existing_by_id.get(item.id)
                if row is None:
                    raise InvalidFeatureEffectDataError(
                        f"{model.__name__} id {item.id} does not belong to this feature/option."
                    )
                for field, value in dump.items():
                    setattr(row, field, value)
                seen_ids.add(item.id)
            else:
                db.add(model(**{owner_field: owner_id}, **dump))

        for row_id, row in existing_by_id.items():
            if row_id not in seen_ids:
                await db.delete(row)

    async def set_fixed_effects(self, feature_id: int, data: FeatureEffectsUpdate) -> FeatureEffectsResponse:
        """
        Diff a feature's fixed effects (all six types) against the payload.

        Choice groups are untouched. After the diff, every character
        currently granted the feature is re-materialized in the same
        transaction (fixed effects apply to all grant holders automatically).
        """

        feature = await self._get_or_404(feature_id)

        await self._diff_owned_rows(FeatureAbilityScoreEffect, "feature_id", feature.id, data.ability_effects)
        await self._diff_owned_rows(FeatureSkillProficiencyEffect, "feature_id", feature.id, data.skill_effects)
        await self._diff_owned_rows(FeatureSavingThrowEffect, "feature_id", feature.id, data.saving_throw_effects)
        await self._diff_owned_rows(FeatureArmorProficiencyEffect, "feature_id", feature.id, data.armor_effects)
        await self._diff_owned_rows(FeatureWeaponProficiencyEffect, "feature_id", feature.id, data.weapon_effects)
        await self._diff_owned_rows(FeatureSpellGrantEffect, "feature_id", feature.id, data.spell_effects)

        # The session runs with autoflush=False — flush the diffed rows so
        # refresh_feature_effect_caches's SELECT-based recomputation
        # (get_feature_increases et al.) actually sees them.
        await self.repository.db.flush()

        await refresh_feature_effect_caches(self.repository.db, feature_id)
        await self.repository.db.commit()
        await purge_feature_cache_for_source(feature.source_type)

        return await self.get_effects(feature_id)

    async def get_choice_groups(self, feature_id: int) -> list[ChoiceGroupResponse]:
        """Return a feature's choice groups with their options and bundles."""

        feature = await self._feature_with_effects(feature_id)
        return [_to_choice_group_response(group) for group in feature.choice_groups]

    async def _diff_choice_options(
        self,
        group: FeatureChoiceGroup,
        option_payloads: list[ChoiceOptionPayload],
        existing_options: dict[int, FeatureChoiceOption],
    ) -> None:
        """
        Diff one group's options — and each surviving/new option's six
        effect-type rows — against ``option_payloads``.

        ``existing_options`` must be passed in by the caller: for an existing
        group it's built from the eager-loaded ``group.options`` collection,
        and for a freshly-flushed NEW group it's ``{}`` — never read
        ``group.options`` here, a lazy load on a new group would trip the
        async session (``greenlet_spawn``).

        A removed option may already be a character's stored pick
        (``CharacterFeatureChoice.choice_option_id``, ``ondelete
        RESTRICT``); rather than blocking the edit, that pick is deleted
        here BEFORE the option itself, so the group reverts to pending for
        that character. ``refresh_feature_effect_caches`` (called once at
        the end of ``set_choice_groups``) then re-materializes every
        character granted the feature, which both strips the removed
        option's effects and recomputes ability totals for anyone affected.
        """

        db = self.repository.db
        seen_option_ids: set[int] = set()
        resolved: list[tuple[FeatureChoiceOption, ChoiceOptionPayload]] = []

        for payload in option_payloads:
            if payload.id is not None:
                option = existing_options.get(payload.id)
                if option is None:
                    raise InvalidFeatureEffectDataError(
                        f"Choice option id {payload.id} does not belong to group {group.id}."
                    )
                option.sort_order = payload.sort_order
                seen_option_ids.add(payload.id)
            else:
                option = FeatureChoiceOption(group_id=group.id, sort_order=payload.sort_order)
                db.add(option)
                await db.flush()  # need option.id before diffing its effect rows

            resolved.append((option, payload))

        # One batched query per effect type across every surviving option in
        # the group, instead of one query per (option, effect type) pair —
        # a group with N options previously ran 6xN SELECTs here.
        effect_dimensions = (
            (FeatureAbilityScoreEffect, "ability_effects"),
            (FeatureSkillProficiencyEffect, "skill_effects"),
            (FeatureSavingThrowEffect, "saving_throw_effects"),
            (FeatureArmorProficiencyEffect, "armor_effects"),
            (FeatureWeaponProficiencyEffect, "weapon_effects"),
            (FeatureSpellGrantEffect, "spell_effects"),
        )
        for model, attr in effect_dimensions:
            existing_by_option = await self._load_owned_rows_by_owner(model, "choice_option_id", seen_option_ids)
            for option, payload in resolved:
                await self._apply_owned_rows_diff(
                    model,
                    "choice_option_id",
                    option.id,
                    getattr(payload, attr),
                    existing_by_option.get(option.id, {}),
                )

        removed_option_ids = [option_id for option_id in existing_options if option_id not in seen_option_ids]
        if removed_option_ids:
            await db.execute(
                delete(CharacterFeatureChoice).where(CharacterFeatureChoice.choice_option_id.in_(removed_option_ids))
            )
        for option_id in removed_option_ids:
            await db.delete(existing_options[option_id])

    async def set_choice_groups(self, feature_id: int, data: ChoiceGroupsUpdate) -> list[ChoiceGroupResponse]:
        """
        Diff a feature's choice groups (and their options/effects) against
        the payload — see the class docstring. Dropping an option or a whole
        group that a character already picked clears that character's
        stored pick (reverting it to pending) instead of failing; every
        character currently granted the feature is then re-materialized.
        """

        feature = await self._get_or_404(feature_id)
        db = self.repository.db

        existing_result = await db.execute(
            select(FeatureChoiceGroup)
            .where(FeatureChoiceGroup.feature_id == feature.id)
            .options(selectinload(FeatureChoiceGroup.options))
        )
        existing_groups = {group.id: group for group in existing_result.unique().scalars().all()}
        seen_group_ids: set[int] = set()

        for payload in data.choice_groups:
            if payload.id is not None:
                group = existing_groups.get(payload.id)
                if group is None:
                    raise InvalidFeatureEffectDataError(f"Choice group id {payload.id} does not belong to this feature.")
                group.pick_count = payload.pick_count
                group.sort_order = payload.sort_order
                group.choice_type = payload.choice_type
                seen_group_ids.add(payload.id)
                existing_options = {option.id: option for option in group.options}
            else:
                group = FeatureChoiceGroup(
                    feature_id=feature.id,
                    pick_count=payload.pick_count,
                    sort_order=payload.sort_order,
                    choice_type=payload.choice_type,
                )
                db.add(group)
                await db.flush()  # need group.id before diffing its options
                existing_options = {}

            await self._diff_choice_options(group, payload.options, existing_options)

        removed_group_ids = [group_id for group_id in existing_groups if group_id not in seen_group_ids]
        if removed_group_ids:
            # Whole group dropped: every character's pick(s) in it revert to
            # pending, same as a removed option — see _diff_choice_options.
            await db.execute(
                delete(CharacterFeatureChoice).where(CharacterFeatureChoice.choice_group_id.in_(removed_group_ids))
            )
        for group_id in removed_group_ids:
            await db.delete(existing_groups[group_id])

        # Flush BEFORE recomputing: the session runs with autoflush=False,
        # so refresh_feature_effect_caches's SELECT-based recomputation
        # would otherwise miss the diffed groups/options/effects. Stale
        # CharacterFeatureChoice rows for anything removed above were
        # already cleared, so this shouldn't trip ON DELETE RESTRICT — the
        # try/except is a safety net for anything that cleanup missed,
        # surfaced as a clean 409 instead of a raw IntegrityError.
        try:
            await db.flush()
            await refresh_feature_effect_caches(self.repository.db, feature_id)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise RecordInUseError(
                model_name="FeatureChoiceOption",
                model_id="one or more removed options/groups",
                reason="still referenced by a character's answered choice",
            ) from exc

        await purge_feature_cache_for_source(feature.source_type)

        return await self.get_choice_groups(feature_id)
