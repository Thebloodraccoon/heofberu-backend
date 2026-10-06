"""Effect-engine repository: every query and row write behind ``FeatureEffectsService``."""

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.constants import EFFECT_TYPE_BY_CHOICE_TYPE
from app.features.features.crud.repository import FeatureRepository, load_effect_flags
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.features.feature_engine_models import EFFECT_TYPES, FeatureChoiceGroup, FeatureChoiceOption
from app.models.features.feature_model import Feature

_ATTR_BY_EFFECT_TYPE = dict(EFFECT_TYPES)


class FeatureEffectsRepository(FeatureRepository):
    """:class:`FeatureRepository` plus the effect-row / choice-group queries behind the point writes."""

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

    async def list_choice_groups(self, feature_id: int, *, refresh: bool = False) -> list[FeatureChoiceGroup]:
        """A feature's choice groups with their options loaded (no effect rows); ``refresh`` re-reads loaded ones."""

        statement = (
            select(FeatureChoiceGroup)
            .where(FeatureChoiceGroup.feature_id == feature_id)
            .options(selectinload(FeatureChoiceGroup.options))
            .order_by(FeatureChoiceGroup.sort_order, FeatureChoiceGroup.id)
        )
        if refresh:
            statement = statement.execution_options(populate_existing=True)

        return list((await self.db.execute(statement)).unique().scalars().all())

    async def get_choice_group_tree(self, feature_id: int) -> list[FeatureChoiceGroup]:
        """
        A feature's choice groups with options and every option effect loaded, ordered for responses.

        A group's options carry only the one effect type its ``choice_type`` allows, so only that type is
        queried (one query per type present) and the other collections are set empty: 2 + k queries, not 2 + 6.
        """

        groups = await self.list_choice_groups(feature_id, refresh=True)
        options = [option for group in groups for option in group.options]

        option_ids_by_attr: dict[str, list[int]] = {attr: [] for _, attr in EFFECT_TYPES}
        for group in groups:
            attr = _ATTR_BY_EFFECT_TYPE[EFFECT_TYPE_BY_CHOICE_TYPE[group.choice_type]]
            option_ids_by_attr[attr].extend(option.id for option in group.options)

        for attr, option_ids in option_ids_by_attr.items():
            rows_by_option = await self._option_effect_rows(attr, option_ids)
            for option in options:
                set_committed_value(option, attr, rows_by_option.get(option.id, []))

        return groups

    async def _option_effect_rows(self, attr: str, option_ids: list[int]) -> dict[int, list[Any]]:
        """The ``attr`` effect rows of the given options (one query, none when there are no options), by option id."""

        if not option_ids:
            return {}

        model = getattr(FeatureChoiceOption, attr).property.mapper.class_
        statement = (
            select(model)
            .where(model.choice_option_id.in_(option_ids))
            .order_by(model.id)
            .execution_options(populate_existing=True)
        )
        by_option: dict[int, list[Any]] = {}
        for row in (await self.db.execute(statement)).scalars():
            by_option.setdefault(row.choice_option_id, []).append(row)

        return by_option

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

    async def clear_character_picks(self, *, option_ids: Sequence[int] = (), group_ids: Sequence[int] = ()) -> None:
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

        Must run after the change was flushed (so the existence query sees the
        rows just written) and before the transaction commits: these two
        columns are what ``GET /features``/``GET /feats`` listings read.
        """

        flags = (await load_effect_flags(self.db, [feature.id]))[feature.id]
        feature.has_static_effects = flags["has_static_effects"]
        feature.has_choices = flags["has_choices"]
