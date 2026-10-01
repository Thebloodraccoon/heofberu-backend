"""
Feat repository: CRUD over the unified ``features`` table, scoped to FEAT-source rows.

A feat IS a ``Feature`` (see ``app/models/feature_model.py``): this
repository is a thin, ``source_type='FEAT'``-scoped view over the shared
``features``/engine-effect tables, not a separate model. Every query here
filters to ``FEAT`` so a feat endpoint can never leak or mutate a
class/subclass/race/subrace/background feature.
"""

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ChoiceType, FeatureSourceType
from app.core.base.repository import BaseRepository
from app.core.db_errors import is_unique_violation
from app.core.exceptions import RecordAlreadyExistsError
from app.features.features.crud.repository import feature_summary_loads
from app.models.character.character_asi_choice_model import CharacterASIChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
)
from app.models.features.feature_model import Feature


def _feat_scope(filters: dict | None) -> dict:
    """``filters`` pinned to FEAT-source rows."""

    return {**(filters or {}), "source_type": FeatureSourceType.FEAT}


def _raise_if_name_conflict(exc: IntegrityError, data: dict) -> None:
    """Turn a unique violation (a concurrent duplicate name) into ``RecordAlreadyExistsError``."""

    if is_unique_violation(exc) and data.get("name") is not None:
        raise RecordAlreadyExistsError(model_name="Feat", field="name", value=data["name"]) from exc


def feat_ability_score_effects(feature: Feature) -> list[FeatureAbilityScoreEffect]:
    """
    The flattened list of a FEAT feature's ability-score-increase
    alternatives, in display order — one entry per option in its (at most
    one) choice group. Requires ``choice_groups.options.ability_effects``
    eager-loaded (see ``feature_summary_loads``). Shared by the feat CRUD
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
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def get_by_id(self, model_id: int) -> Feature | None:
        """
        Fetch a FEAT-source feature with its whole effect tree, or ``None``
        (including when it exists but isn't a FEAT).

        A feat's response exposes ``static_groups``/``effects_summary`` (plain
        ``Feature`` properties reading every effect relationship and the
        choice-group tree), so anything narrower would lazy-load during
        serialization and fail on the async engine.
        """

        result = await self.db.execute(
            select(Feature)
            .where(Feature.id == model_id, Feature.source_type == FeatureSourceType.FEAT)
            .options(*feature_summary_loads())
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def get_row(self, model_id: int) -> Feature | None:
        """Fetch the FEAT-source feature row alone, without its effect tree (enough for update/delete)."""

        result = await self.db.execute(
            select(Feature).where(Feature.id == model_id, Feature.source_type == FeatureSourceType.FEAT)
        )
        return result.scalars().first()

    async def exists_by_id(self, model_id: int) -> bool:
        """Whether ``model_id`` is a FEAT-source feature."""

        stmt = select(Feature.id).where(Feature.id == model_id, Feature.source_type == FeatureSourceType.FEAT)
        return await self.db.scalar(stmt.limit(1)) is not None

    async def get_brief(self, *columns, filters=None, **kwargs) -> list:
        """Column-select page of FEAT-source features only (see :class:`BaseRepository`)."""

        return await super().get_brief(*columns, filters=_feat_scope(filters), **kwargs)

    async def count(self, *, filters=None, search=None) -> int:
        """Count FEAT-source features only (see :class:`BaseRepository`)."""

        return await super().count(filters=_feat_scope(filters), search=search)

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

        try:
            return await super().create({**obj_data, "source_type": FeatureSourceType.FEAT}, commit=commit)
        except IntegrityError as exc:
            _raise_if_name_conflict(exc, obj_data)
            raise

    async def update(self, db_obj: Feature, update_data: dict, *, refresh: bool = False) -> Feature:
        """Apply ``update_data``; a concurrent duplicate name surfaces as ``RecordAlreadyExistsError``."""

        try:
            return await super().update(db_obj, update_data, refresh=refresh)
        except IntegrityError as exc:
            _raise_if_name_conflict(exc, update_data)
            raise

    async def is_in_use(self, feat_id: int) -> bool:
        """Check whether a character holds the feat or an ASI log row points at it (both block deletion)."""

        return await self.exists_referencing(CharacterFeature, "feature_id", feat_id) or await self.exists_referencing(
            CharacterASIChoice, "feat_id", feat_id
        )

    async def delete(self, db_obj: Feature) -> bool:
        """
        Delete the feat unless a character holds it.

        ``character_features.feature_id`` cascades, so a grant slipping in
        between the guard and the DELETE would be wiped silently. Locking the
        feature row first makes a concurrent grant (which takes a key-share
        lock on it) wait for this transaction.
        """

        await self.db.execute(select(Feature.id).where(Feature.id == db_obj.id).with_for_update())
        return await super().delete(db_obj)

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

        This is the feat's own choice-group table (not shared with fixed
        effects), so it also maintains ``feat.has_choices`` directly here —
        ``has_static_effects`` is untouched: ASI options never carry a fixed
        effect, only a per-option one.
        """

        await self.db.execute(delete(FeatureChoiceGroup).where(FeatureChoiceGroup.feature_id == feat.id))
        feat.has_choices = bool(increases)

        if increases:
            group = FeatureChoiceGroup(
                feature_id=feat.id,
                pick_count=1,
                sort_order=0,
                choice_type=ChoiceType.ABILITY_SCORE,
                options=[
                    FeatureChoiceOption(
                        sort_order=index,
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
