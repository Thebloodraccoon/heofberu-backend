"""Feature repository: base CRUD plus engine-effect management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.features.feature_engine_models import (
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSkillProficiencyEffect,
    FeatureSpellGrantEffect,
    FeatureWeaponProficiencyEffect,
)
from app.models.features.feature_model import Feature


class FeatureRepository(BaseRepository[Feature]):
    """
    Feature-specific repository built on :class:`BaseRepository`.

    Listing and detail reads both eager-load the whole effect tree
    via ``default_load_options`` so ``FeatureResponse`` serializes
    without lazy loads.
    """

    def __init__(self, db: AsyncSession):
        """Configure the repository with its model, eager loads, and search fields."""

        super().__init__(
            Feature,
            db,
            default_load_options=feature_summary_loads(),
            search_fields=["name"],
        )

    async def get_by_id(self, model_id: int) -> Feature | None:
        """Fetch a feature by id with its full engine effect tree eager-loaded."""

        result = await self.db.execute(
            select(Feature)
            .where(Feature.id == model_id)
            .options(*feature_summary_loads())
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def get_with_effects(self, feature_id: int, *, fallback: Feature | None = None) -> Feature:
        """
        Fetch a feature with its full engine effect tree loaded.

        ``fallback`` is the already-fetched row (used so callers that got a
        404 signal can re-raise); when the eager query returns nothing the
        fallback row is returned as-is.
        """

        result = await self.db.execute(select(Feature).where(Feature.id == feature_id).options(*feature_summary_loads()))
        feature = result.scalars().first()
        return feature if feature is not None else fallback


# The catalog relationship each effect type resolves its display name
# through — shared between a feature's FIXED rows and its choice-OPTION
# rows (same model classes either way, see feature_engine_models.py).
_NAME_RELATIONSHIP_BY_EFFECT_ATTR = {
    "skill_effects": FeatureSkillProficiencyEffect.skill,
    "weapon_effects": FeatureWeaponProficiencyEffect.item,
    "spell_effects": FeatureSpellGrantEffect.spell,
}

_EFFECT_ATTRS = (
    "ability_effects",
    "skill_effects",
    "saving_throw_effects",
    "armor_effects",
    "weapon_effects",
    "spell_effects",
)


def feature_summary_loads(base=None) -> list:
    """
    Full eager-load set for a ``Feature``'s engine effect tree — fixed
    effects, choice groups/options with their own effects, and the
    skill/spell/item relationships those effects need to render a NAME
    (not just an id). Every response exposing ``has_static_effects``/
    ``has_choices``/``effects_summary`` needs this: they're plain
    ``Feature`` properties, populated by ``from_attributes`` off whatever's
    eager-loaded here — nothing async happens at serialization time.

    Pass a ``base`` loader (a ``selectinload`` for a ``Feature``-valued
    relationship, e.g. ``selectinload(Background.features)``) to chain onto
    it when querying a parent that embeds features; omit it when querying
    ``Feature`` rows directly.
    """

    def load(attr):
        return selectinload(attr) if base is None else base.selectinload(attr)

    loads = []
    for attr in _EFFECT_ATTRS:
        fixed_load = load(getattr(Feature, attr))
        name_relationship = _NAME_RELATIONSHIP_BY_EFFECT_ATTR.get(attr)
        if name_relationship is not None:
            fixed_load = fixed_load.selectinload(name_relationship)
        loads.append(fixed_load)

    options_load = load(Feature.choice_groups).selectinload(FeatureChoiceGroup.options)
    for attr in _EFFECT_ATTRS:
        option_load = options_load.selectinload(getattr(FeatureChoiceOption, attr))
        name_relationship = _NAME_RELATIONSHIP_BY_EFFECT_ATTR.get(attr)
        if name_relationship is not None:
            option_load = option_load.selectinload(name_relationship)
        loads.append(option_load)

    return loads
