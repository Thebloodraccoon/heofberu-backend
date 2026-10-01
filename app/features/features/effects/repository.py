"""Effect-engine repository: every query and row write behind ``FeatureEffectsService``."""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.features.features.crud.repository import EFFECT_ATTRS, FeatureRepository, load_effect_flags
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption
from app.models.features.feature_model import Feature


class FeatureEffectsRepository(FeatureRepository):
    """:class:`FeatureRepository` plus the effect-row / choice-group queries the diff engine needs."""

    async def load_owned_rows(
        self, model: Any, owner_field: str, owner_ids: Iterable[int]
    ) -> dict[int, dict[int, Any]]:
        """``model`` rows owned by any of ``owner_ids`` (one query), as ``{owner_id: {row_id: row}}``."""

        owner_ids = set(owner_ids)
        if not owner_ids:
            return {}

        owner_column = getattr(model, owner_field)
        rows = (await self.db.execute(select(model).where(owner_column.in_(owner_ids)))).scalars().all()

        by_owner: dict[int, dict[int, Any]] = {}
        for row in rows:
            by_owner.setdefault(getattr(row, owner_field), {})[row.id] = row

        return by_owner

    async def list_choice_groups(self, feature_id: int) -> list[FeatureChoiceGroup]:
        """A feature's choice groups with their options loaded (no effect rows)."""

        result = await self.db.execute(
            select(FeatureChoiceGroup)
            .where(FeatureChoiceGroup.feature_id == feature_id)
            .options(selectinload(FeatureChoiceGroup.options))
            .order_by(FeatureChoiceGroup.sort_order, FeatureChoiceGroup.id)
        )
        return list(result.unique().scalars().all())

    async def get_choice_group_tree(self, feature_id: int) -> list[FeatureChoiceGroup]:
        """A feature's choice groups with options and every option effect loaded, ordered for responses."""

        options_load = selectinload(FeatureChoiceGroup.options)
        result = await self.db.execute(
            select(FeatureChoiceGroup)
            .where(FeatureChoiceGroup.feature_id == feature_id)
            .options(*(options_load.selectinload(getattr(FeatureChoiceOption, attr)) for attr in EFFECT_ATTRS))
            .order_by(FeatureChoiceGroup.sort_order, FeatureChoiceGroup.id)
            .execution_options(populate_existing=True)
        )
        return list(result.unique().scalars().all())

    def add(self, *rows: Any) -> None:
        """Stage new rows for insert."""

        self.db.add_all(rows)

    async def remove(self, rows: Iterable[Any]) -> None:
        """Stage ``rows`` for deletion."""

        for row in rows:
            await self.db.delete(row)

    async def flush(self) -> None:
        """Push staged changes (the session runs with ``autoflush=False``)."""

        await self.db.flush()

    async def clear_character_picks(self, *, option_ids: list[int] = (), group_ids: list[int] = ()) -> None:
        """Delete every character's stored pick of the given options/groups (the pick reverts to pending)."""

        if option_ids:
            await self.db.execute(
                delete(CharacterFeatureChoice).where(CharacterFeatureChoice.choice_option_id.in_(option_ids))
            )
        if group_ids:
            await self.db.execute(
                delete(CharacterFeatureChoice).where(CharacterFeatureChoice.choice_group_id.in_(group_ids))
            )

    async def missing_ids(self, model: Any, ids: Iterable[int]) -> list[int]:
        """The subset of ``ids`` that match no ``model`` row (one query)."""

        wanted = set(ids)
        if not wanted:
            return []

        found = set((await self.db.execute(select(model.id).where(model.id.in_(wanted)))).scalars().all())
        return sorted(wanted - found)

    async def refresh_effect_flags(self, feature: Feature) -> None:
        """
        Recompute and store ``feature.has_static_effects``/``has_choices``.

        Must run after the diff was flushed (so the existence query sees the
        rows just written) and before the transaction commits: these two
        columns are what ``GET /features``/``GET /feats`` listings read.
        """

        flags = (await load_effect_flags(self.db, [feature.id]))[feature.id]
        feature.has_static_effects = flags["has_static_effects"]
        feature.has_choices = flags["has_choices"]
