"""Spell repository: base CRUD plus class/subclass/race/subrace availability management."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Integer, Table, cast, exists, literal_column, null, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import Class, Race, Spell, Subclass, Subrace
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_spell_model import CharacterGrantedSpell, CharacterSpell
from app.models.features.feature_engine_models import FeatureSpellGrantEffect
from app.models.spells.spell_association_models import (
    spell_classes,
    spell_races,
    spell_subclasses,
    spell_subraces,
)


@dataclass(frozen=True)
class AvailabilityDimension:
    """One axis a spell's availability is restricted along (classes, subclasses, races, subraces)."""

    field: str
    label: str
    model: Any
    table: Table
    child_fk: str
    parent_fk: str | None = None  # the child's parent column, sent with each ref (a subclass's ``class_id``)


AVAILABILITY_DIMENSIONS = (
    AvailabilityDimension("available_classes", "Classes", Class, spell_classes, "class_id"),
    AvailabilityDimension("available_subclasses", "Subclasses", Subclass, spell_subclasses, "subclass_id", "class_id"),
    AvailabilityDimension("available_races", "Races", Race, spell_races, "race_id"),
    AvailabilityDimension("available_subraces", "Subraces", Subrace, spell_subraces, "subrace_id", "race_id"),
)

_DIMENSION_BY_FIELD = {dimension.field: dimension for dimension in AVAILABILITY_DIMENSIONS}


def availability_dimension(field: str) -> AvailabilityDimension:
    """The availability dimension for a ``Spell`` relationship name such as ``"available_classes"``."""

    return _DIMENSION_BY_FIELD[field]


class SpellRepository(BaseRepository[Spell]):
    """Spell-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialise with default load options and name uniqueness."""

        super().__init__(
            Spell,
            db,
            default_load_options=[
                selectinload(getattr(Spell, dimension.field)) for dimension in AVAILABILITY_DIMENSIONS
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    def _apply_filters(self, stmt: Any, filters: dict[str, Any] | None) -> Any:
        """
        The base column filters, plus ``available_to`` (``{class_id, subclass_id, race_id, subrace_id}``):
        only the spells a character with those values may learn — the rule of
        ``characters/spells/eligibility.py``: on every dimension the spell is unrestricted or lists the
        value, and a ``None`` value fails a restricted dimension.
        """

        filters = dict(filters or {})
        if (available_to := filters.pop("available_to", None)) is not None:
            for dimension in AVAILABILITY_DIMENSIONS:
                linked = dimension.table.c.spell_id == Spell.id
                condition = ~exists().where(linked)
                if (value := available_to.get(dimension.child_fk)) is not None:
                    condition = or_(condition, exists().where(linked, dimension.table.c[dimension.child_fk] == value))
                stmt = stmt.where(condition)

        return super()._apply_filters(stmt, filters)

    async def get_plain(self, spell_id: int) -> Spell | None:
        """Fetch the bare spell row without its availability collections (writes that don't serialize it)."""

        return await self.db.get(Spell, spell_id)

    async def update(self, db_obj: Spell, update_data: dict[str, Any], *, refresh: bool = False) -> Spell:
        """Apply ``update_data`` onto ``db_obj`` and flush; the caller owns the transaction."""

        await self._check_uniqueness(update_data, exclude_id=db_obj.id)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        await self.flush()
        if refresh:
            await self.db.refresh(db_obj)

        return db_obj

    async def is_in_use(self, spell_id: int) -> bool:
        """
        Whether a character knows, was granted or picked the spell (an open "any spell" option), or a feature
        effect grants it (blocks deletion).
        """

        for referencing_model in (CharacterSpell, CharacterGrantedSpell, FeatureSpellGrantEffect):
            if await self.exists_referencing(referencing_model, "spell_id", spell_id):
                return True

        return await self.exists_referencing(CharacterFeatureChoice, "picked_spell_id", spell_id)

    async def get_dimension_members(self, dimension: AvailabilityDimension, ids: list[int]) -> list[Any]:
        """Fetch the dimension's catalog rows (classes, races, ...) matching ``ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(dimension.model, ids)

    async def set_availability(self, spell_id: int, dimension: AvailabilityDimension, child_ids: list[int]) -> None:
        """Replace all of a spell's links along one dimension, via the association table to avoid a lazy load."""

        await self.replace_association(
            dimension.table,
            Spell(id=spell_id),
            "spell_id",
            dimension.child_fk,
            list(dict.fromkeys(child_ids)),
        )

    async def load_availability(self, spell_ids: list[int]) -> dict[int, dict[str, list[dict[str, Any]]]]:
        """
        Every availability link of ``spell_ids`` in one ``UNION ALL`` query,
        as ``{spell_id: {dimension field: [{id, name[, class_id | race_id]}]}}`` ordered by child name.
        """

        if not spell_ids:
            return {}

        union = union_all(
            *(
                select(
                    dimension.table.c.spell_id.label("spell_id"),
                    literal_column(f"'{dimension.field}'").label("dimension"),
                    dimension.model.id.label("child_id"),
                    dimension.model.name.label("child_name"),
                    (
                        getattr(dimension.model, dimension.parent_fk) if dimension.parent_fk else cast(null(), Integer)
                    ).label("parent_id"),
                )
                .join(dimension.model, dimension.model.id == dimension.table.c[dimension.child_fk])
                .where(dimension.table.c.spell_id.in_(spell_ids))
                for dimension in AVAILABILITY_DIMENSIONS
            )
        ).subquery()
        rows = await self.db.execute(
            select(union).order_by(union.c.spell_id, union.c.dimension, union.c.child_name, union.c.child_id)
        )

        result: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for spell_id, field, child_id, child_name, parent_id in rows.all():
            ref = {"id": child_id, "name": child_name}
            if parent_fk := _DIMENSION_BY_FIELD[field].parent_fk:
                ref[parent_fk] = parent_id
            result.setdefault(spell_id, {}).setdefault(field, []).append(ref)

        return result
