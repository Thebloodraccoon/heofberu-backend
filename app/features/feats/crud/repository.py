"""
Feat repository: CRUD over the unified ``features`` table, scoped to FEAT-source rows.

A feat IS a ``Feature`` (see ``app/models/feature_model.py``): this
repository is a thin, ``source_type='FEAT'``-scoped view over the shared
``features``/engine-effect tables, not a separate model. Every query here
filters to ``FEAT`` so a feat endpoint can never leak or mutate a
class/subclass/race/subrace/background feature.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.features.features.crud.repository import _engine_effect_loads
from app.models.character.character_feature_model import CharacterFeature
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
)
from app.models.features.feature_model import Feature

# A feat's ASI options live under at most one choice group (pick_count=1);
# fixed (feature_id-owned) ability effects are never used for FEAT rows —
# even a single ASI option is modeled as a one-option group, since taking a
# feat with any ASI option has always required an explicit, confirmed pick.
_FEAT_LOAD_OPTIONS = [
    selectinload(Feature.choice_groups)
    .selectinload(FeatureChoiceGroup.options)
    .selectinload(FeatureChoiceOption.ability_effects),
]


def feat_ability_score_effects(feature: Feature) -> list[FeatureAbilityScoreEffect]:
    """
    The flattened list of a FEAT feature's ability-score-increase
    alternatives, in display order — one entry per option in its (at most
    one) choice group. Requires ``choice_groups.options.ability_effects``
    eager-loaded (see ``_FEAT_LOAD_OPTIONS``). Shared by the feat CRUD
    response builder and the character-side grant validation, so both read
    the same "what can this feat's ASI pick be" logic.
    """

    return [
        effect
        for group in feature.choice_groups
        for option in sorted(group.options, key=lambda o: o.sort_order)
        for effect in option.ability_effects
    ]


class FeatRepository(BaseRepository[Feature]):
    """
    Feat-specific repository built on :class:`BaseRepository`, scoped to
    ``Feature`` rows with ``source_type == FEAT``.
    """

    def __init__(self, db: AsyncSession):
        """Configure the repository with its model, eager loads, and delete guard."""

        super().__init__(
            Feature,
            db,
            default_load_options=_FEAT_LOAD_OPTIONS,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def get_by_id(self, model_id: int) -> Feature | None:
        """Fetch a FEAT-source feature by id, or ``None`` (including when it exists but isn't a FEAT)."""

        result = await self.db.execute(
            select(Feature)
            .where(Feature.id == model_id, Feature.source_type == FeatureSourceType.FEAT)
            .options(*_engine_effect_loads())
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def get_all(self, *, skip=0, limit=100, filters=None, search=None, order_by=None):
        """List FEAT-source features only (see :class:`BaseRepository`)."""

        filters = {**(filters or {}), "source_type": FeatureSourceType.FEAT}
        return await super().get_all(skip=skip, limit=limit, filters=filters, search=search, order_by=order_by)

    async def count(self, *, filters=None, search=None) -> int:
        """Count FEAT-source features only (see :class:`BaseRepository`)."""

        filters = {**(filters or {}), "source_type": FeatureSourceType.FEAT}
        return await super().count(filters=filters, search=search)

    async def _check_uniqueness(self, data, exclude_id: int | None = None) -> None:
        """
        Feat names must be unique among FEAT-source features only — unlike
        the base implementation, an unscoped check would false-positive
        against an unrelated class/race feature that happens to share a name
        (``features.name`` carries no DB-level unique constraint at all).
        """

        name = data.get("name")
        if name is None:
            return

        stmt = select(Feature.id).where(Feature.source_type == FeatureSourceType.FEAT, Feature.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Feature.id != exclude_id)

        if await self.db.scalar(stmt) is not None:
            raise RecordAlreadyExistsError(model_name="Feat", field="name", value=name)

    async def create(self, obj_data: dict, *, commit: bool = True) -> Feature:
        """Create a FEAT-source feature (``source_type`` is pinned, never taken from the payload)."""

        return await super().create({**obj_data, "source_type": FeatureSourceType.FEAT}, commit=commit)

    async def is_in_use(self, feat_id: int) -> bool:
        """Check whether the feat is currently granted to any character, which blocks deletion."""

        return await self.exists_referencing(CharacterFeature, "feature_id", feat_id)

    async def set_ability_score_increases(
        self, feat: Feature, increases: list[dict], *, commit: bool = True
    ) -> Feature:
        """
        Replace a feat's ASI options.

        Deletes any existing choice group (cascades away its options and
        their ability effects), then — when ``increases`` is non-empty —
        creates exactly ONE new group (``pick_count=1``) with one option per
        alternative. Uniform even for a single option: the API has always
        required an explicit ``ability_score_increase_id`` whenever a feat
        offers any ASI choice (see ``validate_asi_choice_required``), so a
        lone option is still a confirmed pick, never auto-applied.
        """

        await self.db.execute(delete(FeatureChoiceGroup).where(FeatureChoiceGroup.feature_id == feat.id))

        if increases:
            group = FeatureChoiceGroup(
                feature_id=feat.id,
                pick_count=1,
                sort_order=0,
                label="Ability Score Increase",
                options=[
                    FeatureChoiceOption(
                        sort_order=index,
                        label=str(getattr(item["ability"], "value", item["ability"])),
                        ability_effects=[
                            FeatureAbilityScoreEffect(ability=item["ability"], amount=item["amount"], new_cap=None)
                        ],
                    )
                    for index, item in enumerate(increases)
                ],
            )
            self.db.add(group)

        await self.commit_or_flush(commit=commit)

        return feat
