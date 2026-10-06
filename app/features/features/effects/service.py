"""Feature effects service: point reads and writes of the effect engine of a feature."""

from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import EFFECT_TYPE_BY_CHOICE_TYPE, ChoiceType
from app.core.base.transaction import TransactionMixin
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.characters.progression.feature_sync import refresh_feature_effect_caches
from app.features.features.cache import invalidate_feature_cache_after_commit
from app.features.features.effects.exceptions import InvalidFeatureEffectDataError
from app.features.features.effects.repository import FeatureEffectsRepository
from app.features.features.effects.schemas import (
    DUPLICATE_KEY_BY_EFFECT_FIELD,
    ITEM_BY_EFFECT_TYPE,
    MAX_CHOICE_GROUPS,
    ChoiceGroupPatch,
    ChoiceGroupPayload,
    ChoiceGroupResponse,
    ChoiceOptionPatch,
    ChoiceOptionPayload,
    FeatureEffectsResponse,
    FeatureEffectsUpdate,
)
from app.models import Item, Skill, Spell
from app.models.features.feature_engine_models import (
    EFFECT_TYPES,
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

_MODEL_BY_EFFECT_TYPE = {
    "ability": FeatureAbilityScoreEffect,
    "skill": FeatureSkillProficiencyEffect,
    "saving_throw": FeatureSavingThrowEffect,
    "armor": FeatureArmorProficiencyEffect,
    "weapon": FeatureWeaponProficiencyEffect,
    "spell": FeatureSpellGrantEffect,
}

# (effect row model, attribute name on the payload/response schemas) per effect type, in ``EFFECT_TYPES`` order;
# a type missing from ``_MODEL_BY_EFFECT_TYPE`` fails at import.
_EFFECT_DIMENSIONS = tuple((_MODEL_BY_EFFECT_TYPE[effect_type], attr) for effect_type, attr in EFFECT_TYPES)

# Catalog model behind each referencing effect field: (schema field, id attribute, label, model).
_CATALOG_REFERENCES = (
    ("skill_effects", "skill_id", "skill_id", Skill),
    ("weapon_effects", "item_id", "item_id", Item),
    ("spell_effects", "spell_id", "spell_id", Spell),
)


class FeatureEffectsService(TransactionMixin):
    """
    Everything about a feature's effects: its choice groups ("pick N of M",
    each option a bundle of effects) and its fixed automatic effects across
    the six typed tables.

    Every write touches **one** row (or one new group/option with its
    bundle): fixed effects, choice groups, options and an option's effects
    each have their own create / update / delete. Each write is one
    transaction (``unit_of_work``): the row change, the denormalized
    ``has_*`` flags, the stat-cache refresh of every granted character
    (``refresh_feature_effect_caches``; their other effects are computed on
    read) and the post-commit cache purge. ``CharacterFeatureChoice.choice_option_id``
    is ``ondelete RESTRICT``, so deleting an option/group first deletes the
    stored picks of it (the pick reverts to pending).
    """

    repository: FeatureEffectsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the service with the effect-engine repository."""

        self.repository = FeatureEffectsRepository(db)

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    @asynccontextmanager
    async def _write(self) -> AsyncGenerator[None, None]:
        """One transaction; a character's pick that lands on a row being deleted (RESTRICT FK) is a 409."""

        try:
            async with self._unit_of_work():
                yield
        except IntegrityError as exc:
            if "character_feature_choices" not in str(exc.orig):
                raise
            raise RecordInUseError(
                model_name="FeatureChoiceOption",
                model_id="the option/group being removed",
                reason="a character has just picked it",
            ) from exc

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
            # plain dicts, validated into the static-group union by pydantic
            static_groups=feature.static_groups,  # type: ignore[arg-type]
        )

    async def get_choice_groups(self, feature_id: int) -> list[ChoiceGroupResponse]:
        """Return a feature's choice groups with their options and bundles."""

        await self._get_feature_or_404(feature_id)
        return await self._choice_group_responses(feature_id)

    async def _choice_group_responses(self, feature_id: int) -> list[ChoiceGroupResponse]:
        groups = await self.repository.get_choice_group_tree(feature_id)
        return [ChoiceGroupResponse.model_validate(group) for group in groups]

    async def _ensure_targets_exist(self, owners: Iterable[Any]) -> None:
        """422 for any skill/item/spell id the payloads reference but the catalog lacks."""

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

    @staticmethod
    def _validated(groups: list) -> FeatureEffectsUpdate:
        """Run the fixed-effect validators (concrete skill/spell, no duplicates...) over ``groups``; 422 on failure."""

        try:
            return FeatureEffectsUpdate(static_groups=groups)
        except ValidationError as exc:
            raise InvalidFeatureEffectDataError("; ".join(error["msg"] for error in exc.errors())) from exc

    @staticmethod
    def _new_rows(owner_field: str, owner_id: int, data: Any) -> list:
        """Effect rows for every item of ``data`` (per-type ``*_effects`` lists), owned by ``owner_id``."""

        rows = []
        for model, field_name in _EFFECT_DIMENSIONS:
            for item in getattr(data, field_name) or []:
                if item.id is not None:
                    raise InvalidFeatureEffectDataError("New effects must not carry an id.")
                rows.append(model(**{owner_field: owner_id}, **item.model_dump(exclude={"id"})))
        return rows

    async def _owned_rows(self, model: Any, owner_field: str, owner_id: int) -> dict[int, Any]:
        """The owner's rows of ``model`` as ``{row_id: row}`` (one query)."""

        return (await self.repository.load_owned_rows(model, owner_field, [owner_id])).get(owner_id, {})

    @staticmethod
    def _row_or_404(model: Any, rows: dict[int, Any], effect_id: int) -> Any:
        row = rows.get(effect_id)
        if row is None:
            raise RecordNotFoundError(model_name=model.__name__, model_id=str(effect_id))

        return row

    @staticmethod
    def _reject_existing_duplicates(
        field_name: str, items: list, rows: dict[int, Any], skip_id: int | None = None
    ) -> None:
        """422 when an item equals (same duplicate key) a row the owner already has, bar ``skip_id``."""

        key = DUPLICATE_KEY_BY_EFFECT_FIELD[field_name]
        taken = {key(row) for row_id, row in rows.items() if row_id != skip_id}
        if any(key(item) in taken for item in items):
            raise InvalidFeatureEffectDataError(f"An equal {field_name} entry already exists.")

    async def _add_effects(self, feature: Feature, owner_field: str, owner_id: int, data: FeatureEffectsUpdate) -> None:
        rows = self._new_rows(owner_field, owner_id, data)
        if not rows:
            return

        await self._ensure_targets_exist([data])
        for model, field_name in _EFFECT_DIMENSIONS:
            if items := getattr(data, field_name):
                owned = await self._owned_rows(model, owner_field, owner_id)
                self._reject_existing_duplicates(field_name, items, owned)

        async with self._write():
            self.repository.add(*rows)
            await self._finish_write(feature)

    async def _update_effect(
        self, feature: Feature, owner_field: str, owner_id: int, effect_type: str, effect_id: int, changes: dict
    ) -> None:
        """PATCH one effect row: ``changes`` over its current values, validated as a whole item."""

        model = _MODEL_BY_EFFECT_TYPE[effect_type]
        owned = await self._owned_rows(model, owner_field, owner_id)
        row = self._row_or_404(model, owned, effect_id)

        current = ITEM_BY_EFFECT_TYPE[effect_type].model_validate(row).model_dump(exclude={"id"})
        data = self._validated([{"effect_type": effect_type, "items": [{**current, **changes}]}])
        await self._ensure_targets_exist([data])
        field_name = f"{effect_type}_effects"
        self._reject_existing_duplicates(field_name, getattr(data, field_name), owned, skip_id=effect_id)

        async with self._write():
            for field, value in getattr(data, field_name)[0].model_dump(exclude={"id"}).items():
                setattr(row, field, value)
            await self._finish_write(feature)

    async def _remove_effect(
        self, feature: Feature, owner_field: str, owner_id: int, effect_type: str, effect_id: int
    ) -> None:
        model = _MODEL_BY_EFFECT_TYPE[effect_type]
        row = self._row_or_404(model, await self._owned_rows(model, owner_field, owner_id), effect_id)

        async with self._write():
            await self.repository.remove([row])
            await self._finish_write(feature)

    async def _finish_write(self, feature: Feature, *, effects_changed: bool = True) -> None:
        """
        Flush the change and schedule the cache purge; when ``effects_changed``, also refresh the ``has_*``
        flags and every granted character (an order-only change leaves what they read untouched).
        """

        await self.repository.flush()
        if effects_changed:
            await self.repository.refresh_effect_flags(feature)
            await refresh_feature_effect_caches(self.repository.db, feature.id)
        await invalidate_feature_cache_after_commit(self.repository.db, feature.source_type)

    async def add_fixed_effects(self, feature_id: int, data: FeatureEffectsUpdate) -> FeatureEffectsResponse:
        """Insert the payload's items as new fixed-effect rows; existing rows are never touched."""

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        await self._add_effects(feature, "feature_id", feature.id, data)
        return await self.get_effects(feature_id)

    async def update_fixed_effect(
        self, feature_id: int, effect_type: str, effect_id: int, changes: dict
    ) -> FeatureEffectsResponse:
        """Change fields of one fixed-effect row (404 when it isn't this feature's)."""

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        await self._update_effect(feature, "feature_id", feature.id, effect_type, effect_id, changes)
        return await self.get_effects(feature_id)

    async def remove_fixed_effect(self, feature_id: int, effect_type: str, effect_id: int) -> FeatureEffectsResponse:
        """Delete one fixed-effect row (404 when it isn't this feature's)."""

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        await self._remove_effect(feature, "feature_id", feature.id, effect_type, effect_id)
        return await self.get_effects(feature_id)

    async def _group_or_404(self, feature_id: int, group_id: int) -> FeatureChoiceGroup:
        group = next((g for g in await self.repository.list_choice_groups(feature_id) if g.id == group_id), None)
        if group is None:
            raise RecordNotFoundError(model_name="FeatureChoiceGroup", model_id=str(group_id))

        return group

    @staticmethod
    def _option_or_404(group: FeatureChoiceGroup, option_id: int) -> FeatureChoiceOption:
        option = next((o for o in group.options if o.id == option_id), None)
        if option is None:
            raise RecordNotFoundError(model_name="FeatureChoiceOption", model_id=str(option_id))

        return option

    async def _locked_group(self, feature_id: int, group_id: int) -> tuple[Feature, FeatureChoiceGroup]:
        """The row-locked feature and one of its groups (404 when either is missing)."""

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        return feature, await self._group_or_404(feature.id, group_id)

    async def _locked_option(
        self, feature_id: int, group_id: int, option_id: int
    ) -> tuple[Feature, FeatureChoiceGroup, FeatureChoiceOption]:
        """The row-locked feature, one of its groups and an option of that group (404 when any is missing)."""

        feature, group = await self._locked_group(feature_id, group_id)
        return feature, group, self._option_or_404(group, option_id)

    @staticmethod
    def _check_effects_fit(group: FeatureChoiceGroup, data: Any) -> None:
        """A group's options may carry only the one effect type its ``choice_type`` allows."""

        allowed = EFFECT_TYPE_BY_CHOICE_TYPE[group.choice_type]
        for _, field_name in _EFFECT_DIMENSIONS:
            if field_name != f"{allowed}_effects" and getattr(data, field_name):
                raise InvalidFeatureEffectDataError(
                    f"A '{group.choice_type.value}' group's options may only carry '{allowed}' effects."
                )

    async def add_choice_group(self, feature_id: int, payload: ChoiceGroupPayload) -> list[ChoiceGroupResponse]:
        """Create a group, optionally with its options and their effects (no ids anywhere in the payload)."""

        feature = await self._get_feature_or_404(feature_id, for_update=True)
        if payload.id is not None or any(option.id is not None for option in payload.options):
            raise InvalidFeatureEffectDataError("A new choice group and its options must not carry an id.")
        await self._ensure_targets_exist(payload.options)

        repo = self.repository
        existing = await repo.list_choice_groups(feature.id)
        if len(existing) >= MAX_CHOICE_GROUPS:
            raise InvalidFeatureEffectDataError(f"A feature may have at most {MAX_CHOICE_GROUPS} choice groups.")
        if payload.choice_type == ChoiceType.ABILITY_SCORE and any(
            group.choice_type == ChoiceType.ABILITY_SCORE for group in existing
        ):
            # feat_ability_score_effects (and every ASI answer path) assumes one ABILITY_SCORE group per feature
            raise InvalidFeatureEffectDataError("A feature may have at most one choice group of type ABILITY_SCORE.")

        async with self._write():
            group = FeatureChoiceGroup(
                feature_id=feature.id,
                pick_count=payload.pick_count,
                sort_order=payload.sort_order,
                choice_type=payload.choice_type,
            )
            repo.add(group)
            await repo.flush()

            options = [FeatureChoiceOption(group_id=group.id, sort_order=o.sort_order) for o in payload.options]
            repo.add(*options)
            await repo.flush()

            for option, option_payload in zip(options, payload.options, strict=True):
                repo.add(*self._new_rows("choice_option_id", option.id, option_payload))
            await self._finish_write(feature)

        return await self._choice_group_responses(feature_id)

    async def update_choice_group(
        self, feature_id: int, group_id: int, data: ChoiceGroupPatch
    ) -> list[ChoiceGroupResponse]:
        """Change a group's ``pick_count`` / ``sort_order``."""

        feature, group = await self._locked_group(feature_id, group_id)

        changes = data.model_dump(exclude_unset=True)
        if changes:
            async with self._write():
                for field, value in changes.items():
                    setattr(group, field, value)
                await self._finish_write(feature, effects_changed="pick_count" in changes)

        return await self._choice_group_responses(feature_id)

    async def remove_choice_group(self, feature_id: int, group_id: int) -> list[ChoiceGroupResponse]:
        """Delete a group with its options; characters' picks of it revert to pending."""

        feature, group = await self._locked_group(feature_id, group_id)

        async with self._write():
            await self.repository.clear_character_picks(
                option_ids=[option.id for option in group.options], group_ids=[group.id]
            )
            await self.repository.remove([group])
            await self._finish_write(feature)

        return await self._choice_group_responses(feature_id)

    async def add_choice_option(
        self, feature_id: int, group_id: int, payload: ChoiceOptionPayload
    ) -> list[ChoiceGroupResponse]:
        """Create an option (with its effect bundle) in a group."""

        feature, group = await self._locked_group(feature_id, group_id)
        if payload.id is not None:
            raise InvalidFeatureEffectDataError("A new choice option must not carry an id.")
        self._validated(payload.effects)
        self._check_effects_fit(group, payload)
        await self._ensure_targets_exist([payload])

        async with self._write():
            option = FeatureChoiceOption(group_id=group.id, sort_order=payload.sort_order)
            self.repository.add(option)
            await self.repository.flush()
            self.repository.add(*self._new_rows("choice_option_id", option.id, payload))
            await self._finish_write(feature)

        return await self._choice_group_responses(feature_id)

    async def update_choice_option(
        self, feature_id: int, group_id: int, option_id: int, data: ChoiceOptionPatch
    ) -> list[ChoiceGroupResponse]:
        """Change an option's ``sort_order``."""

        feature, _, option = await self._locked_option(feature_id, group_id, option_id)

        async with self._write():
            option.sort_order = data.sort_order
            await self._finish_write(feature, effects_changed=False)

        return await self._choice_group_responses(feature_id)

    async def remove_choice_option(self, feature_id: int, group_id: int, option_id: int) -> list[ChoiceGroupResponse]:
        """Delete an option; characters' picks of it revert to pending."""

        feature, _, option = await self._locked_option(feature_id, group_id, option_id)

        async with self._write():
            await self.repository.clear_character_picks(option_ids=[option.id])
            await self.repository.remove([option])
            await self._finish_write(feature)

        return await self._choice_group_responses(feature_id)

    async def add_option_effects(
        self, feature_id: int, group_id: int, option_id: int, data: FeatureEffectsUpdate
    ) -> list[ChoiceGroupResponse]:
        """Insert new effect rows into an option's bundle."""

        feature, group, option = await self._locked_option(feature_id, group_id, option_id)
        self._check_effects_fit(group, data)

        await self._add_effects(feature, "choice_option_id", option.id, data)
        return await self._choice_group_responses(feature_id)

    async def update_option_effect(
        self, feature_id: int, group_id: int, option_id: int, effect_type: str, effect_id: int, changes: dict
    ) -> list[ChoiceGroupResponse]:
        """Change fields of one effect row of an option's bundle."""

        feature, _, option = await self._locked_option(feature_id, group_id, option_id)

        await self._update_effect(feature, "choice_option_id", option.id, effect_type, effect_id, changes)
        return await self._choice_group_responses(feature_id)

    async def remove_option_effect(
        self, feature_id: int, group_id: int, option_id: int, effect_type: str, effect_id: int
    ) -> list[ChoiceGroupResponse]:
        """Delete one effect row of an option's bundle."""

        feature, _, option = await self._locked_option(feature_id, group_id, option_id)

        await self._remove_effect(feature, "choice_option_id", option.id, effect_type, effect_id)
        return await self._choice_group_responses(feature_id)
