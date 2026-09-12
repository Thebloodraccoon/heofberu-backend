"""Feature effects service: read/write the effect engine on the reference side (Phase 3)."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.characters.progression.feature_sync import refresh_feature_effect_caches
from app.features.features.cache import FEATURE_CACHE_NAMESPACES, purge_feature_cache_for_source
from app.features.features.crud.repository import FeatureRepository
from app.features.features.crud.schemas import FeatureResponse
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
        label=group.label,
        choice_type=group.choice_type,
        options=option_responses,
    )


class FeatureEffectsService(BaseService[Feature, None, None, FeatureResponse, None]):
    """
    Everything about a feature's effects: its choice groups ("pick N of M",
    each option a bundle of effects) and its fixed automatic effects across
    the six typed tables.

    All writes are full replaces inside the caller's transaction and purge
    the ``features`` cache. Because
    an effect edit can change what granted characters receive, every write
    also re-materializes the granted characters' effect rows via
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
            ability_effects=[AbilityEffectItem.model_validate(e) for e in feature.ability_effects],
            skill_effects=[SkillEffectItem.model_validate(e) for e in feature.skill_effects],
            saving_throw_effects=[SavingThrowEffectItem.model_validate(e) for e in feature.saving_throw_effects],
            armor_effects=[ArmorEffectItem.model_validate(e) for e in feature.armor_effects],
            weapon_effects=[WeaponEffectItem.model_validate(e) for e in feature.weapon_effects],
            spell_effects=[SpellEffectItem.model_validate(e) for e in feature.spell_effects],
        )

    async def set_fixed_effects(self, feature_id: int, data: FeatureEffectsUpdate) -> FeatureEffectsResponse:
        """
        Fully replace a feature's fixed effects (all six types).

        Choice groups are untouched. After the replace, every character
        currently granted the feature is re-materialized in the same
        transaction (fixed effects apply to all grant holders automatically).
        """

        feature = await self._get_or_404(feature_id)

        async def _replace(model, items: list, dumps) -> None:
            """Delete the feature's fixed rows of one effect type and insert the new ones."""
            db = self.repository.db
            await db.execute(delete(model).where(model.feature_id == feature.id))
            db.add_all([model(feature_id=feature.id, **dump) for dump in dumps])

        await _replace(FeatureAbilityScoreEffect, data.ability_effects, [e.model_dump() for e in data.ability_effects])
        await _replace(FeatureSkillProficiencyEffect, data.skill_effects, [e.model_dump() for e in data.skill_effects])
        await _replace(
            FeatureSavingThrowEffect,
            data.saving_throw_effects,
            [e.model_dump() for e in data.saving_throw_effects],
        )
        await _replace(FeatureArmorProficiencyEffect, data.armor_effects, [e.model_dump() for e in data.armor_effects])
        await _replace(
            FeatureWeaponProficiencyEffect, data.weapon_effects, [e.model_dump() for e in data.weapon_effects]
        )
        await _replace(FeatureSpellGrantEffect, data.spell_effects, [e.model_dump() for e in data.spell_effects])

        # The session runs with autoflush=False — flush the newly added rows
        # so refresh_feature_effect_caches's SELECT-based recomputation
        # (get_feature_increases et al.) actually sees them, instead of
        # silently recomputing off the just-deleted (now empty) old set.
        await self.repository.db.flush()

        await refresh_feature_effect_caches(self.repository.db, feature_id)
        await self.repository.db.commit()
        await purge_feature_cache_for_source(feature.source_type)

        return await self.get_effects(feature_id)

    async def get_choice_groups(self, feature_id: int) -> list[ChoiceGroupResponse]:
        """Return a feature's choice groups with their options and bundles."""

        feature = await self._feature_with_effects(feature_id)
        return [_to_choice_group_response(group) for group in feature.choice_groups]

    async def set_choice_groups(self, feature_id: int, data: ChoiceGroupsUpdate) -> list[ChoiceGroupResponse]:
        """
        Fully replace a feature's choice groups (and their options/effects).

        Full replace via delete-orphan cascade: the given tree becomes the
        complete set. Grants that already answered the old tree keep their
        rows pointing at still-existing options; stale options' effects are
        re-materialized by the caller's re-sync.
        """

        feature = await self._get_or_404(feature_id)
        db = self.repository.db

        existing = await db.execute(select(FeatureChoiceGroup).where(FeatureChoiceGroup.feature_id == feature.id))
        for group in existing.scalars().all():
            await db.delete(group)

        def _make_option(payload: ChoiceOptionPayload) -> FeatureChoiceOption:
            return FeatureChoiceOption(
                sort_order=payload.sort_order,
                ability_effects=[FeatureAbilityScoreEffect(**e.model_dump()) for e in payload.ability_effects],
                skill_effects=[FeatureSkillProficiencyEffect(**e.model_dump()) for e in payload.skill_effects],
                saving_throw_effects=[FeatureSavingThrowEffect(**e.model_dump()) for e in payload.saving_throw_effects],
                armor_effects=[FeatureArmorProficiencyEffect(**e.model_dump()) for e in payload.armor_effects],
                weapon_effects=[FeatureWeaponProficiencyEffect(**e.model_dump()) for e in payload.weapon_effects],
                spell_effects=[FeatureSpellGrantEffect(**e.model_dump()) for e in payload.spell_effects],
            )

        for payload in data.choice_groups:
            db.add(
                FeatureChoiceGroup(
                    feature_id=feature.id,
                    pick_count=payload.pick_count,
                    sort_order=payload.sort_order,
                    label=payload.label,
                    choice_type=payload.choice_type,
                    options=[_make_option(option) for option in payload.options],
                )
            )

        # Flush BEFORE recomputing: the session runs with autoflush=False,
        # so refresh_feature_effect_caches's SELECT-based recomputation
        # would otherwise miss the newly added groups/options/effects.
        await db.flush()
        await refresh_feature_effect_caches(self.repository.db, feature_id)
        await db.commit()
        await purge_feature_cache_for_source(feature.source_type)

        return await self.get_choice_groups(feature_id)
