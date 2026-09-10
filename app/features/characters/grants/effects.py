"""
Shared loader: what a feature/feat grant actually did to a character —
its materialized effect rows (scoped by ``source_character_feature_id``)
and the player's stored picks for its choice groups.

Used by both ``features`` and ``feats`` so a character's feature/feat
listing can show not just "you have this" but "here's what it gave you".
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterGrantedSpellResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterWeaponProficiencyResponse,
    ChosenOptionResponse,
    GrantedSkillEffectResponse,
    GrantEffectsResponse,
)
from app.features.characters.spells.repository import spell_response_loads
from app.models.character_association_models import CharacterSkillProficiency
from app.models.character_engine_models import (
    CharacterArmorProficiency,
    CharacterGrantedSpell,
    CharacterSavingThrowProficiency,
    CharacterWeaponProficiency,
)
from app.models.character_feature_model import CharacterFeature


async def get_grant_effects_map(db: AsyncSession, grant_ids: list[int]) -> dict[int, GrantEffectsResponse]:
    """
    Batch-load the materialized effect rows for every grant in
    ``grant_ids``, grouped by ``source_character_feature_id`` — one query
    per effect type rather than one per grant, for listing endpoints.
    """

    effects_by_grant = {grant_id: GrantEffectsResponse() for grant_id in grant_ids}
    if not grant_ids:
        return effects_by_grant

    skills = await db.execute(
        select(CharacterSkillProficiency).where(
            CharacterSkillProficiency.source_character_feature_id.in_(grant_ids)
        )
    )
    for row in skills.scalars().unique().all():
        effects_by_grant[row.source_character_feature_id].skills.append(
            GrantedSkillEffectResponse.model_validate(row)
        )

    saves = await db.execute(
        select(CharacterSavingThrowProficiency).where(
            CharacterSavingThrowProficiency.source_character_feature_id.in_(grant_ids)
        )
    )
    for row in saves.scalars().unique().all():
        effects_by_grant[row.source_character_feature_id].saving_throws.append(
            CharacterSavingThrowProficiencyResponse.model_validate(row)
        )

    armor = await db.execute(
        select(CharacterArmorProficiency).where(
            CharacterArmorProficiency.source_character_feature_id.in_(grant_ids)
        )
    )
    for row in armor.scalars().unique().all():
        effects_by_grant[row.source_character_feature_id].armor.append(
            CharacterArmorProficiencyResponse.model_validate(row)
        )

    weapons = await db.execute(
        select(CharacterWeaponProficiency).where(
            CharacterWeaponProficiency.source_character_feature_id.in_(grant_ids)
        )
    )
    for row in weapons.scalars().unique().all():
        effects_by_grant[row.source_character_feature_id].weapons.append(
            CharacterWeaponProficiencyResponse.model_validate(row)
        )

    spells = await db.execute(
        select(CharacterGrantedSpell)
        .options(*spell_response_loads(selectinload(CharacterGrantedSpell.spell)))
        .where(CharacterGrantedSpell.source_character_feature_id.in_(grant_ids))
    )
    for row in spells.scalars().unique().all():
        effects_by_grant[row.source_character_feature_id].spells.append(
            CharacterGrantedSpellResponse.model_validate(row)
        )

    return effects_by_grant


async def get_grant_effects(db: AsyncSession, grant_id: int) -> GrantEffectsResponse:
    """Fetch the materialized effect rows for a single grant (see :func:`get_grant_effects_map`)."""

    return (await get_grant_effects_map(db, [grant_id]))[grant_id]


def build_chosen_options(grant: CharacterFeature) -> list[ChosenOptionResponse]:
    """
    Build the player's resolved picks for a grant from its stored
    ``CharacterFeatureChoice`` rows. Requires ``grant.choices`` (and each
    choice's ``choice_option``) to already be eager-loaded.
    """

    return [
        ChosenOptionResponse(
            choice_group_id=choice.choice_group_id,
            choice_option_id=choice.choice_option_id,
            label=choice.choice_option.label if choice.choice_option is not None else "",
        )
        for choice in grant.choices
    ]
