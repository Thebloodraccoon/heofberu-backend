"""
Auto-grant/revoke source-owned features for a character.

A character automatically holds every feature owned by its class
(CLASS), chosen subclass (SUBCLASS), race (RACE), chosen subrace
(SUBRACE) and background (BACKGROUND), filtered by ``level``: ``NULL``
(gained at level 1) or ``<= character.level``. This module reconciles
``character_features`` against that target set. Feats grant no features
(a feat is de facto its own feature).

It is deliberately small and side-effect free (never commits): callers
wrap it in their own transaction — ``CharacterService.create_character``,
``CharacterProgressionService`` (level-up, subclass/subrace change)
and ``GmPanelFeatService`` (feat grant/revoke).

Rows it does not own are left untouched: features created manually from
OTHER sources, and any notes a player wrote on a grant, survive
reconciliation unless the grant's own feature leaves the auto-granted
set (e.g. the character changes class or drops a subclass).
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.cache import invalidate_character_cache
from app.models import CharacterFeature, Feature
from app.models.character_model import Character

_AUTO_SOURCE_TYPES = (
    FeatureSourceType.CLASS,
    FeatureSourceType.SUBCLASS,
    FeatureSourceType.RACE,
    FeatureSourceType.SUBRACE,
    FeatureSourceType.BACKGROUND,
)

_SOURCE_CHARACTER_FILTER = {
    FeatureSourceType.CLASS: lambda source_id: Character.class_id == source_id,
    FeatureSourceType.SUBCLASS: lambda source_id: Character.subclass_id == source_id,
    FeatureSourceType.RACE: lambda source_id: Character.race_id == source_id,
    FeatureSourceType.SUBRACE: lambda source_id: Character.subrace_id == source_id,
    FeatureSourceType.BACKGROUND: lambda source_id: Character.background_id == source_id,
}


async def _desired_features(db: AsyncSession, character: Character) -> list[Feature]:
    """
    The target feature set for a character: features owned by its class,
    subclass, race, subrace, and background, all filtered to ``level``
    ``NULL`` or ``<= character.level``.
    """

    conditions = []
    if character.class_id is not None:
        conditions.append(Feature.class_id == character.class_id)

    if character.subclass_id is not None:
        conditions.append(Feature.subclass_id == character.subclass_id)

    if character.race_id is not None:
        conditions.append(Feature.race_id == character.race_id)

    if character.subrace_id is not None:
        conditions.append(Feature.subrace_id == character.subrace_id)

    if character.background_id is not None:
        conditions.append(Feature.background_id == character.background_id)

    if not conditions:
        return []

    result = await db.execute(
        select(Feature).where(or_(*conditions)).where(or_(Feature.level.is_(None), Feature.level <= character.level))
    )
    return list(result.scalars().unique().all())


async def sync_progression_features(db: AsyncSession, character: Character) -> None:
    """
    Reconcile ``character_features`` to match the character's current
    class/subclass/race/subrace/background/feats/level. Adds missing
    grants, revokes auto-granted features that no longer apply, and leaves
    everything else alone.
    """

    desired = await _desired_features(db, character)
    desired_ids = {feature.id for feature in desired}

    result = await db.execute(
        select(CharacterFeature)
        .options(selectinload(CharacterFeature.feature))
        .where(CharacterFeature.character_id == character.id)
    )

    existing = list(result.scalars().unique().all())
    existing_ids = {grant.feature_id for grant in existing}

    for grant in existing:
        feature = grant.feature
        if feature is not None and feature.source_type in _AUTO_SOURCE_TYPES and grant.feature_id not in desired_ids:
            await db.delete(grant)

    for feature in desired:
        if feature.id not in existing_ids:
            db.add(CharacterFeature(character_id=character.id, feature_id=feature.id, notes=""))


async def reconcile_characters_for_source(db: AsyncSession, source_type: FeatureSourceType, source_id: int) -> None:
    """
    Re-run :func:`sync_progression_features` for every character affected
    by a change to a source's feature set.

    Called by the source replace endpoints (``PUT /{source}/{id}/features``)
    inside their ``_atomic()`` block, so a GM editing a class/race/
    subrace/background's features reconciles the affected characters'
    grants in the same transaction:

      - features added to the source are granted to qualifying characters
        (level-gated by :func:`_desired_features`);
      - features whose ``level`` was raised are revoked from characters
        below the new level (the row survives, so the DB cascade alone
        wouldn't clean the grant);
      - features dropped from the source are removed — their ``Feature``
        row is deleted by the replace helper, so the ``ON DELETE CASCADE``
        clears the grants.

    Each source filters ``Character`` by its own FK. Never commits — the
    caller's transaction owns persistence.
    """

    source_filter = _SOURCE_CHARACTER_FILTER.get(source_type)
    if source_filter is None:
        return

    result = await db.execute(select(Character).where(source_filter(source_id)))
    characters = list(result.scalars().unique().all())

    stats_service = CharacterStatsService(db)
    for character in characters:
        await sync_progression_features(db, character)
        # Feature grants can carry fixed ability effects — refresh the
        # stat cache in the caller's transaction (never commits here).
        await stats_service.refresh(character, commit=False)
        await invalidate_character_cache(character.id)


async def refresh_feature_effect_caches(db: AsyncSession, feature_id: int) -> None:
    """
    Refresh the ability-score caches of every character currently granted
    ``feature``. Called after a GM edits the feature's fixed
    ability-increase effects (``PUT /features/ability-increases``) so the
    granted characters' totals follow immediately instead of waiting for
    the per-character self-heal on the next detail fetch.

    Never commits — the caller's transaction owns persistence.
    """

    result = await db.execute(
        select(CharacterFeature.character_id).where(CharacterFeature.feature_id == feature_id)
    )
    character_ids = list(result.scalars().all())
    if not character_ids:
        return

    characters = await db.execute(select(Character).where(Character.id.in_(character_ids)))
    stats_service = CharacterStatsService(db)
    for character in characters.scalars().all():
        await stats_service.refresh(character, commit=False)
