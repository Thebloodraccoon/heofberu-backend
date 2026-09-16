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

from app.constants import ProficiencyType
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
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.character.character_spell_model import CharacterGrantedSpell

_RESPONSE_BY_TYPE = {
    ProficiencyType.SKILL: GrantedSkillEffectResponse,
    ProficiencyType.SAVING_THROW: CharacterSavingThrowProficiencyResponse,
    ProficiencyType.ARMOR: CharacterArmorProficiencyResponse,
    ProficiencyType.WEAPON: CharacterWeaponProficiencyResponse,
}
_LIST_ATTR_BY_TYPE = {
    ProficiencyType.SKILL: "skills",
    ProficiencyType.SAVING_THROW: "saving_throws",
    ProficiencyType.ARMOR: "armor",
    ProficiencyType.WEAPON: "weapons",
}


async def get_grant_effects_map(db: AsyncSession, grant_ids: list[int]) -> dict[int, GrantEffectsResponse]:
    """
    Batch-load the materialized effect rows for every grant in
    ``grant_ids``, grouped by ``source_character_feature_id`` — one query
    for every proficiency kind rather than one per grant, for listing
    endpoints.
    """

    effects_by_grant = {grant_id: GrantEffectsResponse() for grant_id in grant_ids}
    if not grant_ids:
        return effects_by_grant

    proficiencies = await db.execute(
        select(CharacterProficiency).where(CharacterProficiency.source_character_feature_id.in_(grant_ids))
    )
    for row in proficiencies.scalars().unique().all():
        response_type = _RESPONSE_BY_TYPE[ProficiencyType(row.proficiency_type)]
        list_attr = _LIST_ATTR_BY_TYPE[ProficiencyType(row.proficiency_type)]
        getattr(effects_by_grant[row.source_character_feature_id], list_attr).append(
            response_type.model_validate(row)
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
    choice's ``choice_option``, with its six effect-type relationships) to
    already be eager-loaded (see ``choice_option_effect_loads``).
    """

    responses = []
    for choice in grant.choices:
        option = choice.choice_option
        responses.append(
            ChosenOptionResponse(
                choice_group_id=choice.choice_group_id,
                choice_option_id=choice.choice_option_id,
                ability_effects=option.ability_effects if option is not None else [],
                skill_effects=option.skill_effects if option is not None else [],
                saving_throw_effects=option.saving_throw_effects if option is not None else [],
                armor_effects=option.armor_effects if option is not None else [],
                weapon_effects=option.weapon_effects if option is not None else [],
                spell_effects=option.spell_effects if option is not None else [],
            )
        )
    return responses
