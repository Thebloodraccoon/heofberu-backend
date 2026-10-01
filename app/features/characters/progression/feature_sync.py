"""
Auto-grant/revoke source-owned features for characters.

A character automatically holds every feature owned by its class, subclass,
race, subrace, and background, filtered by ``level`` (``NULL`` or
``<= character.level``); this module reconciles ``character_features``
(``grant_source=AUTO``) against that target set. Feats are granted
explicitly (GM panel or ASI choice) — ``FEAT``/``OTHER`` features are never
auto-granted here.

Only grants are stored: what a grant gives (skills, saves, armor/weapons,
spells) is computed on read from the feature's effect tree plus the
player's stored picks (``characters/grants/effects.py``). What still needs
refreshing after a change is the ability-score cache
(``character_ability_scores``) and the per-character Redis payload — the
latter is purged after the caller's commit.

Never commits — callers wrap it in their own transaction:
``CharacterService.create_character``, ``CharacterProgressionService``,
``GmPanelFeatService``, the central ``FeatureCrudService`` and the
race/subrace ability-bonus services.
"""

from sqlalchemy import and_, cast, delete, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType, GrantSource
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.cache import invalidate_characters_cache
from app.models import CharacterFeature, Feature
from app.models.character.character_model import Character
from app.models.enums import GrantSourceType

_SOURCE_COLUMNS = {
    FeatureSourceType.CLASS: (Character.class_id, Feature.class_id),
    FeatureSourceType.SUBCLASS: (Character.subclass_id, Feature.subclass_id),
    FeatureSourceType.RACE: (Character.race_id, Feature.race_id),
    FeatureSourceType.SUBRACE: (Character.subrace_id, Feature.subrace_id),
    FeatureSourceType.BACKGROUND: (Character.background_id, Feature.background_id),
}


def _level_reached():
    """SQL condition: the feature's ``level`` is unset or reached by the joined character."""

    return or_(Feature.level.is_(None), Feature.level <= Character.level)


async def _desired_feature_ids(db: AsyncSession, character: Character) -> set[int]:
    """
    Ids of the target feature set for a character: features owned by its
    class, subclass, race, subrace, and background, filtered to ``level``
    ``NULL`` or ``<= character.level``.
    """

    conditions = [
        feature_column == getattr(character, character_column.key)
        for character_column, feature_column in _SOURCE_COLUMNS.values()
        if getattr(character, character_column.key) is not None
    ]
    if not conditions:
        return set()

    result = await db.execute(
        select(Feature.id).where(or_(*conditions), or_(Feature.level.is_(None), Feature.level <= character.level))
    )
    return set(result.scalars().all())


async def sync_progression_features(db: AsyncSession, character: Character) -> list[CharacterFeature]:
    """
    Reconcile ``character_features`` to match the character's current
    class/subclass/race/subrace/background/level, keeping FEAT/OTHER grants
    and GM manual grants. Revoking an auto-grant cascades its stored picks
    away. Never commits — ``db.flush()`` is used so callers can read new
    grant ids.

    Returns the grants newly added by this call (empty on a no-op sync).
    Callers that must not silently skip a newly-unlocked feature's
    "pick N of M" (e.g. level-up) use this to know which grants to check
    for pending choice groups.
    """

    desired_ids = await _desired_feature_ids(db, character)

    result = await db.execute(select(CharacterFeature).where(CharacterFeature.character_id == character.id))
    existing = list(result.scalars().unique().all())
    existing_ids = {grant.feature_id for grant in existing}

    for grant in existing:
        if grant.grant_source == GrantSource.AUTO and grant.feature_id not in desired_ids:
            await db.delete(grant)

    new_grants = [
        CharacterFeature(character_id=character.id, feature_id=feature_id, grant_source=GrantSource.AUTO)
        for feature_id in sorted(desired_ids - existing_ids)
    ]
    db.add_all(new_grants)
    await db.flush()

    return new_grants


async def _refresh_after_change(db: AsyncSession, characters: list[Character]) -> None:
    """
    Grants can carry ability effects: refresh every affected character's
    stat cache in this transaction (batched, see
    ``CharacterStatsService.compute_many``) and purge their Redis payloads in
    one round trip once it has committed.
    """

    await CharacterStatsService(db).refresh_many(characters, commit=False)

    await invalidate_characters_cache((character.id for character in characters), db=db)


async def reconcile_characters_for_source(db: AsyncSession, source_type: FeatureSourceType, source_id: int) -> None:
    """
    Bring every character owning ``source_type``/``source_id`` in line with
    that source's current feature set (called by ``FeatureCrudService`` and
    the race/subrace ability-bonus services, in their transaction): newly
    added or now-reached features are granted, features whose ``level``
    was raised above a character's level are revoked (their picks cascade
    away), deleted features already cleared their grants via ``ON DELETE
    CASCADE``. Two set-based statements for all characters at once — no
    per-character loop. Then refreshes the affected characters' stat caches
    and Redis payloads. Never commits.
    """

    columns = _SOURCE_COLUMNS.get(source_type)
    if columns is None:
        return
    character_column, feature_column = columns

    # The statements below read features straight from the DB: push pending edits (e.g. a raised ``level``) first.
    await db.flush()

    characters = list(
        (await db.execute(select(Character).where(character_column == source_id))).scalars().unique().all()
    )
    if not characters:
        return

    await db.execute(
        delete(CharacterFeature).where(
            CharacterFeature.grant_source == GrantSource.AUTO,
            CharacterFeature.character_id == Character.id,
            CharacterFeature.feature_id == Feature.id,
            character_column == source_id,
            feature_column == source_id,
            ~_level_reached(),
        )
    )

    await db.execute(
        pg_insert(CharacterFeature)
        .from_select(
            ["character_id", "feature_id", "grant_source"],
            select(Character.id, Feature.id, cast(literal(GrantSource.AUTO, GrantSourceType), GrantSourceType))
            .join(Feature, and_(feature_column == source_id, _level_reached()))
            .where(character_column == source_id),
        )
        .on_conflict_do_nothing(index_elements=["character_id", "feature_id"])
    )
    await db.flush()

    await _refresh_after_change(db, characters)


async def refresh_feature_effect_caches(db: AsyncSession, feature_id: int) -> None:
    """
    After a GM edits a feature's effects or choice groups, refresh the
    ability-score cache and the Redis payload of every character currently
    granted it. Their other effects need no work — they are computed on
    read from the edited tree. Never commits.
    """

    result = await db.execute(
        select(Character)
        .join(CharacterFeature, CharacterFeature.character_id == Character.id)
        .where(CharacterFeature.feature_id == feature_id)
    )
    characters = list(result.scalars().unique().all())
    if not characters:
        return

    await _refresh_after_change(db, characters)
