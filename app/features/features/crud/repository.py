"""Feature repository: base CRUD plus the effect-tree loaders shared by every catalog."""

from typing import Any

from sqlalchemy import Select, literal_column, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.core.base.repository import BaseRepository
from app.models.character.character_asi_choice_model import CharacterASIChoice
from app.models.character.character_feature_model import CharacterFeature
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

_STATIC_EFFECT_MODELS = (
    FeatureAbilityScoreEffect,
    FeatureSkillProficiencyEffect,
    FeatureSavingThrowEffect,
    FeatureArmorProficiencyEffect,
    FeatureWeaponProficiencyEffect,
    FeatureSpellGrantEffect,
)

# The catalog relationship each effect type resolves its display name
# through — shared between a feature's FIXED rows and its choice-OPTION
# rows (same model classes either way, see feature_engine_models.py).
_NAME_RELATIONSHIP_BY_EFFECT_ATTR = {
    "skill_effects": FeatureSkillProficiencyEffect.skill,
    "weapon_effects": FeatureWeaponProficiencyEffect.item,
    "spell_effects": FeatureSpellGrantEffect.spell,
}

EFFECT_ATTRS = (
    "ability_effects",
    "skill_effects",
    "saving_throw_effects",
    "armor_effects",
    "weapon_effects",
    "spell_effects",
)


def feature_summary_loads(base=None, *, with_names: bool = True) -> list:
    """
    Full eager-load set for a ``Feature``'s engine effect tree — fixed
    effects, choice groups/options with their own effects, and (unless
    ``with_names=False``) the skill/spell/item relationships those effects
    need to render a NAME. Every response exposing ``static_groups``/
    ``effects_summary`` needs the names: they're plain ``Feature``
    properties, populated off whatever's eager-loaded here, so nothing async
    happens at serialization time. The effect-engine endpoints return ids
    only and pass ``with_names=False`` (6 queries fewer).

    Pass a ``base`` loader (a ``selectinload`` for a ``Feature``-valued
    relationship, e.g. ``selectinload(Background.features)``) to chain onto
    it when querying a parent that embeds features; omit it when querying
    ``Feature`` rows directly.
    """

    def load(attr):
        return selectinload(attr) if base is None else base.selectinload(attr)

    def with_name(loader, effect_attr):
        name_relationship = _NAME_RELATIONSHIP_BY_EFFECT_ATTR.get(effect_attr)
        return loader.selectinload(name_relationship) if with_names and name_relationship is not None else loader

    loads = [with_name(load(getattr(Feature, attr)), attr) for attr in EFFECT_ATTRS]

    options_load = load(Feature.choice_groups).selectinload(FeatureChoiceGroup.options)
    loads.extend(
        with_name(options_load.selectinload(getattr(FeatureChoiceOption, attr)), attr) for attr in EFFECT_ATTRS
    )

    return loads


class FeatureRepository(BaseRepository[Feature]):
    """
    Feature-specific repository built on :class:`BaseRepository`.

    ``get_by_id`` eager-loads the whole effect tree so ``FeatureResponse``
    serializes without lazy loads; ``get_plain`` is the cheap fetch for code
    that only needs the row (404 checks, scalar edits, deletes).
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
        """Fetch a feature with its full engine effect tree eager-loaded."""

        return await self._select_one(model_id, feature_summary_loads())

    async def get_with_effect_ids(self, feature_id: int) -> Feature | None:
        """Fetch a feature with the effect tree an id-only response needs (no skill/item/spell names)."""

        return await self._select_one(feature_id, feature_summary_loads(with_names=False))

    async def _select_one(self, feature_id: int, options: list) -> Feature | None:
        result = await self.db.execute(
            select(Feature).where(Feature.id == feature_id).options(*options).execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def get_plain(self, feature_id: int, *, for_update: bool = False) -> Feature | None:
        """
        Fetch the bare feature row, no relationships loaded.

        ``for_update=True`` takes a row lock held until the transaction ends,
        serializing concurrent effect writes on the same feature.
        """

        return await self.db.get(Feature, feature_id, with_for_update=for_update or None)

    async def list_for_source(self, fk_name: str, source_id: int) -> list[Feature]:
        """Every feature whose ``fk_name`` source column equals ``source_id`` (ordered by id, full tree)."""

        result = await self.db.execute(
            select(Feature)
            .where(getattr(Feature, fk_name) == source_id)
            .options(*feature_summary_loads())
            .order_by(Feature.id)
        )
        return list(result.scalars().all())

    async def is_granted(self, feature_id: int) -> bool:
        """Whether any character holds a grant of this feature or an ASI log row points at it (as a feat)."""

        return await self.exists_referencing(
            CharacterFeature, "feature_id", feature_id
        ) or await self.exists_referencing(CharacterASIChoice, "feat_id", feature_id)

    async def holder_character_ids(self, feature_id: int) -> list[int]:
        """Ids of every character currently granted this feature."""

        result = await self.db.execute(
            select(CharacterFeature.character_id).where(CharacterFeature.feature_id == feature_id)
        )
        return list(result.scalars().all())

    async def delete(self, db_obj: Feature, *, commit: bool = True) -> bool:
        """Delete a feature; ``commit=False`` flushes and leaves the transaction to the caller."""

        await self.db.delete(db_obj)
        await self.commit_or_flush(commit=commit)
        return True

    @staticmethod
    def mark_effects_empty(feature: Feature) -> None:
        """
        Tell the ORM a just-created feature's effect collections are loaded
        and empty, so serializing it (``static_groups``, ``effects_summary``)
        never lazy-loads on the async session.
        """

        for attr in (*EFFECT_ATTRS, "choice_groups"):
            set_committed_value(feature, attr, [])


async def load_effect_flags(db, feature_ids: list[int]) -> dict[int, dict[str, bool]]:
    """
    Recompute ``has_static_effects``/``has_choices`` for every id in
    ``feature_ids`` straight from the effect/choice-group tables, in one
    ``UNION ALL`` round trip regardless of how many ids are passed.

    The two flags are real, denormalized ``Feature`` columns: this is the
    write-side source of truth every effect/choice-group mutation calls to
    refresh them (``FeatureEffectsService``), never a listing-time fallback.
    """

    flags = {feature_id: {"has_static_effects": False, "has_choices": False} for feature_id in feature_ids}
    if not feature_ids:
        return flags

    selects: list[Select[Any]] = [
        select(model.feature_id.label("feature_id"), literal_column("'has_static_effects'").label("flag"))
        .where(model.feature_id.in_(feature_ids))
        .distinct()
        for model in _STATIC_EFFECT_MODELS
    ]
    selects.append(
        select(FeatureChoiceGroup.feature_id.label("feature_id"), literal_column("'has_choices'").label("flag"))
        .where(FeatureChoiceGroup.feature_id.in_(feature_ids))
        .distinct()
    )

    for feature_id, flag in (await db.execute(union_all(*selects))).all():
        flags[feature_id][flag] = True

    return flags
