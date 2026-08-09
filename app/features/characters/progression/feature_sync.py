"""
Auto-grant/revoke source-owned features for a character.

A character automatically holds every feature owned by its class
(CLASS), chosen subclass (SUBCLASS), race (RACE), background
(BACKGROUND) and every currently-granted feat (FEAT), filtered by
``level``: ``NULL`` (gained at level 1) or ``<= character.level``.
This module reconciles ``character_features`` against that target set.

It is deliberately small and side-effect free (never commits): callers
wrap it in their own transaction — ``CharacterService.create_character``,
``CharacterProgressionService`` (level-up, race/class/subclass change)
and ``CharacterFeatService`` (feat grant/revoke).

Rows it does not own are left untouched: features created manually from
OTHER sources, and any notes a player wrote on a grant, survive
reconciliation unless the grant's own feature leaves the auto-granted
set (e.g. the character changes class, drops a subclass, or loses a
feat).
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.models import CharacterFeature, Feature
from app.models.character_association_models import CharacterFeat
from app.models.character_model import Character

_AUTO_SOURCE_TYPES = (
    FeatureSourceType.CLASS,
    FeatureSourceType.SUBCLASS,
    FeatureSourceType.RACE,
    FeatureSourceType.BACKGROUND,
    FeatureSourceType.FEAT,
)

_SOURCE_CHARACTER_FILTER = {
    FeatureSourceType.CLASS: lambda source_id: Character.class_id == source_id,
    FeatureSourceType.SUBCLASS: lambda source_id: Character.subclass_id == source_id,
    FeatureSourceType.RACE: lambda source_id: Character.race_id == source_id,
    FeatureSourceType.BACKGROUND: lambda source_id: Character.background_id == source_id,
}


async def _desired_features(db: AsyncSession, character: Character) -> list[Feature]:
    """
    The target feature set for a character: features owned by its class,
    subclass, race, background, and every currently-granted feat, all
    filtered to ``level`` ``NULL`` or ``<= character.level``.
    """

    conditions = []
    if character.class_id is not None:
        conditions.append(Feature.class_id == character.class_id)

    if character.subclass_id is not None:
        conditions.append(Feature.subclass_id == character.subclass_id)

    if character.race_id is not None:
        conditions.append(Feature.race_id == character.race_id)

    if character.background_id is not None:
        conditions.append(Feature.background_id == character.background_id)

    result = await db.execute(select(CharacterFeat.feat_id).where(CharacterFeat.character_id == character.id))
    feat_ids = [feat_id for (feat_id,) in result.all()]
    if feat_ids:
        conditions.append(Feature.feat_id.in_(feat_ids))

    if not conditions:
        return []

    result = await db.execute(
        select(Feature).where(or_(*conditions)).where(or_(Feature.level.is_(None), Feature.level <= character.level))
    )
    return list(result.scalars().unique().all())


async def sync_progression_features(db: AsyncSession, character: Character) -> None:
    """
    Reconcile ``character_features`` to match the character's current
    class/subclass/race/background/feats/level. Adds missing grants,
    revokes auto-granted features that no longer apply, and leaves
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
    background/feat's features reconciles the affected characters' grants
    in the same transaction:

      - features added to the source are granted to qualifying characters
        (level-gated by :func:`_desired_features`);
      - features whose ``level`` was raised are revoked from characters
        below the new level (the row survives, so the DB cascade alone
        wouldn't clean the grant);
      - features dropped from the source are removed — their ``Feature``
        row is deleted by the replace helper, so the ``ON DELETE CASCADE``
        clears the grants.

    FEAT resolves through ``CharacterFeat`` grants (the feat id is not a
    column on ``Character``); every other source filters ``Character`` by
    its own FK. Never commits — the caller's transaction owns persistence.
    """

    if source_type == FeatureSourceType.FEAT:
        result = await db.execute(
            select(Character)
            .join(CharacterFeat, CharacterFeat.character_id == Character.id)
            .where(CharacterFeat.feat_id == source_id)
        )
        characters = list(result.scalars().unique().all())
    else:
        source_filter = _SOURCE_CHARACTER_FILTER.get(source_type)
        if source_filter is None:
            return

        result = await db.execute(select(Character).where(source_filter(source_id)))
        characters = list(result.scalars().unique().all())

    for character in characters:
        await sync_progression_features(db, character)
