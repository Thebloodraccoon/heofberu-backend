"""
Auto-grant/revoke source-owned features for a character, and materialize
their effect rows.

A character automatically holds every feature owned by its class, subclass,
race, subrace, and background, filtered by ``level`` (``NULL`` or
``<= character.level``); this module reconciles ``character_features``
against that target set and then re-materializes the effect rows (skills,
saving throws, armor/weapon proficiencies, granted spells) of every
``grant_source=AUTO`` grant from the feature's fixed effects plus the
player's stored choice picks. Feats are granted explicitly (GM panel or
ASI choice) — ``FEAT``/``OTHER`` features are never auto-granted here.

It is deliberately small and side-effect free (never commits): callers wrap
it in their own transaction — ``CharacterService.create_character``,
``CharacterProgressionService``, ``GmPanelFeatService``, and the central
``FeatureCrudService``. Rows it does not own (manual features from other
sources, GM free-form proficiency rows with a NULL source) are left
untouched. Re-materialization only ever touches rows whose
``source_character_feature_id`` is set, and preserves skill ``is_expertise``
upgrades.

``sync_progression_features`` materializes every one of a character's
auto-grants in one batched pass (Variant A of the
``characters-grant-materialization-batching-plan``: one query per
proficiency-type dimension across the whole grant batch, not one per grant)
— see ``FeatureGrantMaterializer.reconcile_many``. Other callers
(``refresh_feature_effect_caches``, the GM panel, feat grants) still
materialize one grant at a time via ``materialize_grant``/``reconcile``.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType, GrantSource
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.cache import invalidate_characters_cache
from app.features.characters.grants.materializer import (
    FeatureGrantMaterializer,
    ResolvedOption,
    load_feature_effect_tree,
    load_feature_effect_trees,
)
from app.models import CharacterFeature, Feature
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_model import Character

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


async def _grant_choice_map(db: AsyncSession, feature: Feature, grant: CharacterFeature) -> dict[int, list[ResolvedOption]]:
    """
    Rebuild the ``group_id -> [ResolvedOption]`` map for a grant from its
    stored choice rows, resolving each stored option against the eager-loaded
    feature tree. Options that no longer exist on the reference side are
    skipped. Skill resolutions done at answer time are not persisted, so an
    open ("any skill") option contributes nothing on re-materialization —
    the player's concrete skill pick is remembered only in the already-written
    character row, which is left untouched.
    """

    option_by_id = {option.id: option for group in feature.choice_groups for option in group.options}

    result = await db.execute(
        select(CharacterFeatureChoice).where(CharacterFeatureChoice.character_feature_id == grant.id)
    )
    stored = list(result.scalars().unique().all())

    choice_map: dict[int, list[ResolvedOption]] = {}
    for choice in stored:
        option = option_by_id.get(choice.choice_option_id)
        if option is None:
            continue
        choice_map.setdefault(choice.choice_group_id, []).append(ResolvedOption(option=option))
    return choice_map


async def _grant_choice_maps(
    db: AsyncSession, feature_by_id: dict[int, Feature], grants: list[CharacterFeature]
) -> dict[int, dict[int, list[ResolvedOption]]]:
    """
    Batched ``_grant_choice_map``: one query for every grant's stored choice
    rows in ``grants`` instead of one per grant, grouped by
    ``character_feature_id`` before being resolved against each grant's own
    (already batch-loaded) feature tree. A grant whose feature is missing
    from ``feature_by_id`` (vanished reference row) is simply skipped, same
    as ``materialize_grant``'s single-grant behavior.
    """

    grant_ids = [grant.id for grant in grants]
    if not grant_ids:
        return {}

    result = await db.execute(
        select(CharacterFeatureChoice).where(CharacterFeatureChoice.character_feature_id.in_(grant_ids))
    )
    stored_by_grant: dict[int, list[CharacterFeatureChoice]] = {grant_id: [] for grant_id in grant_ids}
    for choice in result.scalars().unique().all():
        stored_by_grant[choice.character_feature_id].append(choice)

    choice_maps: dict[int, dict[int, list[ResolvedOption]]] = {}
    for grant in grants:
        feature = feature_by_id.get(grant.feature_id)
        if feature is None:
            continue

        option_by_id = {option.id: option for group in feature.choice_groups for option in group.options}
        choice_map: dict[int, list[ResolvedOption]] = {}
        for choice in stored_by_grant[grant.id]:
            option = option_by_id.get(choice.choice_option_id)
            if option is None:
                continue
            choice_map.setdefault(choice.choice_group_id, []).append(ResolvedOption(option=option))
        choice_maps[grant.id] = choice_map

    return choice_maps


async def materialize_grant(
    db: AsyncSession, character: Character, grant: CharacterFeature, *, feature: Feature | None = None
) -> None:
    """
    Re-materialize one grant's effect rows (fixed effects + stored picks).
    A grant whose feature vanished is left hanging — the level sync removes
    auto-grants, and GM grants are the GM's to clean up.

    ``feature`` lets a caller that already loaded the effect tree (e.g.
    ``refresh_feature_effect_caches``, where every grant in the batch is for
    the SAME feature) pass it in instead of this function reloading the
    identical ~14-query tree once per grant/character; omit it to load fresh
    (the ``sync_progression_features`` case, where each grant is a different
    feature).
    """

    if feature is None:
        feature = await load_feature_effect_tree(db, grant.feature_id)
    if feature is None:
        return

    choices = await _grant_choice_map(db, feature, grant)
    await FeatureGrantMaterializer().reconcile(db, character.id, grant, feature, choices)


async def sync_progression_features(db: AsyncSession, character: Character) -> list[CharacterFeature]:
    """
    Reconcile ``character_features`` to match the character's current
    class/subclass/race/subrace/background/level, keeping FEAT/OTHER grants
    and GM manual grants. Then re-materialize the effect rows of every
    ``grant_source=AUTO`` grant so newly added features apply
    their skills/saves/armor/weapons/spells and revoked features lose them.
    Never commits — ``db.flush()`` is used so callers can read new grant ids.

    Returns the grants that were newly added by this call (empty on a
    no-op sync). Callers that must not silently skip a newly-unlocked
    feature's "pick N of M" (e.g. level-up) use this to know which grants
    to check for pending choice groups — a brand-new grant's choice groups
    are never pre-answered, so they stay unmaterialized until the player
    resolves them (``FeatureGrantService.answer_choices``).
    """

    desired = await _desired_features(db, character)
    desired_ids = {feature.id for feature in desired}

    result = await db.execute(
        select(CharacterFeature)
        .options()
        .where(CharacterFeature.character_id == character.id)
    )

    existing = list(result.scalars().unique().all())
    existing_ids = {grant.feature_id for grant in existing}

    for grant in existing:
        if grant.grant_source == GrantSource.AUTO and grant.feature_id not in desired_ids:
            await db.delete(grant)

    new_feature_ids = {feature.id for feature in desired if feature.id not in existing_ids}
    for feature_id in new_feature_ids:
        db.add(
            CharacterFeature(
                character_id=character.id,
                feature_id=feature_id,
                grant_source=GrantSource.AUTO,
            )
        )

    # New/revoked grants from the step above need their ids visible.
    await db.flush()

    grants = await db.execute(
        select(CharacterFeature).where(
            CharacterFeature.character_id == character.id,
            CharacterFeature.grant_source == GrantSource.AUTO,
        )
    )
    all_auto_grants = list(grants.scalars().unique().all())

    # Variant A batching (see the grant-materialization-batching plan):
    # load every grant's feature tree and stored choice picks in one pass
    # each, instead of once per grant, then run one materializer pass per
    # proficiency-type dimension across the whole batch instead of once per
    # grant. Per-grant diff semantics (dedup across grants, is_expertise
    # monotonicity) are unchanged — see ``FeatureGrantMaterializer.reconcile_many``.
    feature_by_id = await load_feature_effect_trees(db, [grant.feature_id for grant in all_auto_grants])
    choice_maps = await _grant_choice_maps(db, feature_by_id, all_auto_grants)

    entries = [
        (grant, feature_by_id[grant.feature_id], choice_maps.get(grant.id, {}))
        for grant in all_auto_grants
        if grant.feature_id in feature_by_id
    ]
    await FeatureGrantMaterializer().reconcile_many(db, character.id, entries)

    return [grant for grant in all_auto_grants if grant.feature_id in new_feature_ids]


async def reconcile_characters_for_source(db: AsyncSession, source_type: FeatureSourceType, source_id: int) -> None:
    """
    Re-run ``sync_progression_features`` for every character affected by a
    change to a source's feature set (called by ``FeatureCrudService`` in
    its transaction), so newly added features are granted (and materialized),
    features whose ``level`` was raised are revoked from characters below it
    (their effect rows cascade away on grant deletion), and dropped features
    clear their grants via ``ON DELETE CASCADE``. Also the seed of the
    ``RaceAbilityBonusService``/``SubraceAbilityBonusService`` bonus writes,
    where the per-character stat-cache refresh is exactly the fix for a bonus
    edit that would otherwise leave existing totals stale. Never commits.
    """

    source_filter = _SOURCE_CHARACTER_FILTER.get(source_type)
    if source_filter is None:
        return

    result = await db.execute(select(Character).where(source_filter(source_id)))
    characters = list(result.scalars().unique().all())
    if not characters:
        return

    for character in characters:
        await sync_progression_features(db, character)

    # Feature grants can carry fixed ability effects — refresh every
    # affected character's stat cache in the caller's transaction (never
    # commits here). Batched: one query per bonus/increase dimension across
    # the whole list instead of 4 per character (see
    # CharacterStatsService.compute_many), and one Redis round trip instead
    # of one per character (see invalidate_characters_cache).
    stats_service = CharacterStatsService(db)
    await stats_service.refresh_many(characters, commit=False)
    await invalidate_characters_cache(character.id for character in characters)


async def refresh_feature_effect_caches(db: AsyncSession, feature_id: int) -> None:
    """
    Re-materialize the effect rows of every character currently granted
    ``feature`` and refresh their ability-score caches. Called after a GM
    edits the feature's fixed effects (ability increases, skills, saves,
    armor/weapons, spells, choice groups) so granted characters follow
    immediately instead of waiting for the next progression write.

    Never commits — the caller's transaction owns persistence.
    """

    result = await db.execute(select(CharacterFeature).where(CharacterFeature.feature_id == feature_id))
    grants = list(result.scalars().unique().all())
    if not grants:
        return

    character_ids = {grant.character_id for grant in grants}
    characters = (
        await db.execute(select(Character).where(Character.id.in_(character_ids)))
    ).scalars().unique().all()
    character_by_id = {character.id: character for character in characters}

    # Every grant here is for the SAME feature (the one the GM just edited)
    # — load its effect tree once instead of once per grant/character (see
    # ``materialize_grant``'s ``feature`` param).
    feature = await load_feature_effect_tree(db, feature_id)
    if feature is None:
        return

    for grant in grants:
        character = character_by_id.get(grant.character_id)
        if character is None:
            continue
        await materialize_grant(db, character, grant, feature=feature)

    # The DB cache row was just refreshed, but ``GET /characters/{id}``
    # serves its ability scores from a Redis-cached CharacterResponse —
    # purge it so the new totals are visible immediately. Batched across
    # every affected character (see reconcile_characters_for_source).
    affected_characters = list(character_by_id.values())
    stats_service = CharacterStatsService(db)
    await stats_service.refresh_many(affected_characters, commit=False)
    await invalidate_characters_cache(character.id for character in affected_characters)
