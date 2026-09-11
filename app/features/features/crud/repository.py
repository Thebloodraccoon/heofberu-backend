"""Feature repository: base CRUD plus engine-effect management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption
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
            default_load_options=_engine_effect_loads(),
            search_fields=["name"],
        )

    async def get_by_id(self, model_id: int) -> Feature | None:
        """Fetch a feature by id with its full engine effect tree eager-loaded."""

        result = await self.db.execute(
            select(Feature)
            .where(Feature.id == model_id)
            .options(*_engine_effect_loads())
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

        result = await self.db.execute(select(Feature).where(Feature.id == feature_id).options(*_engine_effect_loads()))
        feature = result.scalars().first()
        return feature if feature is not None else fallback


def _engine_effect_loads() -> list:
    """Eager loads for the whole feature-engine effect tree (choice groups + fixed effects)."""

    option_effect_attrs = (
        "ability_effects",
        "skill_effects",
        "saving_throw_effects",
        "armor_effects",
        "weapon_effects",
        "spell_effects",
    )

    return [
        selectinload(Feature.ability_effects),
        selectinload(Feature.skill_effects),
        selectinload(Feature.saving_throw_effects),
        selectinload(Feature.armor_effects),
        selectinload(Feature.weapon_effects),
        selectinload(Feature.spell_effects),
        *(
            selectinload(Feature.choice_groups)
            .selectinload(FeatureChoiceGroup.options)
            .selectinload(getattr(FeatureChoiceOption, attr))
            for attr in option_effect_attrs
        ),
    ]
