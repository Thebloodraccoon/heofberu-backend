"""
Repository backing the GM proficiency panel: reads the rows and feature
grants behind ONE proficiency and upserts/clears the GM layer of
``character_proficiencies``.

A GM write never touches another source's rows (class/race/background) —
it only ever creates, updates, or deletes the single ``source_type=GM`` row
for one (character, proficiency_type, discriminator). Feature/feat grants
have no rows at all: their proficiencies are computed from the grant, and
:meth:`feature_entries` asks the database for just the grants that give the
one proficiency in question.

Writes only flush; the service owns the transaction.
"""

from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy import and_, null, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.features.characters.grants.effects import SkillClaim
from app.features.characters.proficiencies.resolver import (
    ProficiencyEntry,
    feature_source,
    proficiency_key,
    skill_claim_entry,
)
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.features.feature_engine_models import (
    FeatureArmorProficiencyEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
    FeatureSavingThrowEffect,
    FeatureSkillProficiencyEffect,
    FeatureWeaponProficiencyEffect,
)
from app.models.features.feature_model import Feature

_EFFECT_MODEL: dict[ProficiencyType, Any] = {
    ProficiencyType.SKILL: FeatureSkillProficiencyEffect,
    ProficiencyType.SAVING_THROW: FeatureSavingThrowEffect,
    ProficiencyType.ARMOR: FeatureArmorProficiencyEffect,
    ProficiencyType.WEAPON: FeatureWeaponProficiencyEffect,
}

# Per proficiency kind with open ("any …") effects: (effect target column, the pick's named column).
_OPEN_PICK: dict[ProficiencyType, tuple[str, Any]] = {
    ProficiencyType.SKILL: ("skill_id", CharacterFeatureChoice.picked_skill_id),
    ProficiencyType.SAVING_THROW: ("ability", CharacterFeatureChoice.picked_ability),
}


class CharacterProficiencyGmRepository:
    """Owns the GM layer of ``character_proficiencies`` (all proficiency kinds)."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing proficiency rows."""

        self.db = db

    async def get_rows(
        self, character_id: int, proficiency_type: ProficiencyType, **discriminator
    ) -> list[CharacterProficiency]:
        """Every row (any source) for one (character, proficiency) — the resolution algorithm's input."""

        conditions = [
            CharacterProficiency.character_id == character_id,
            CharacterProficiency.proficiency_type == proficiency_type,
        ]
        for column, value in discriminator.items():
            conditions.append(getattr(CharacterProficiency, column) == value)

        result = await self.db.execute(select(CharacterProficiency).where(*conditions))
        return list(result.scalars().unique().all())

    async def feature_entries(
        self, character_id: int, proficiency_type: ProficiencyType, **discriminator
    ) -> list[ProficiencyEntry]:
        """
        One entry per feature/feat grant of the character whose effects give
        this proficiency — a fixed effect of the feature or an effect of an
        option the player picked (an open "any skill/saving throw" effect matches
        through the skill/ability named for the pick) — fetched with a single targeted query
        instead of loading every grant's whole effect tree. A skill entry
        carries the grant's folded claim (see ``SkillClaim``).
        """

        effect = _EFFECT_MODEL[proficiency_type]
        is_skill = proficiency_type == ProficiencyType.SKILL
        key_conditions = [getattr(effect, column) == value for column, value in discriminator.items()]
        mode = effect.mode if is_skill else null()
        columns = (Feature.id, Feature.name, Feature.source_type, mode.label("mode"))

        picked_conditions = key_conditions
        if proficiency_type in _OPEN_PICK:
            # an open effect (target NULL) gives what the player named for the pick
            target, picked_column = _OPEN_PICK[proficiency_type]
            named = and_(getattr(effect, target).is_(None), picked_column == discriminator[target])
            picked_conditions = [or_(*key_conditions, named)]

        fixed = (
            select(*columns)
            .select_from(Feature)
            .join(effect, effect.feature_id == Feature.id)
            .join(CharacterFeature, CharacterFeature.feature_id == Feature.id)
            .where(CharacterFeature.character_id == character_id, *key_conditions)
        )
        picked = (
            select(*columns)
            .select_from(Feature)
            .join(FeatureChoiceGroup, FeatureChoiceGroup.feature_id == Feature.id)
            .join(FeatureChoiceOption, FeatureChoiceOption.group_id == FeatureChoiceGroup.id)
            .join(effect, effect.choice_option_id == FeatureChoiceOption.id)
            .join(CharacterFeature, CharacterFeature.feature_id == Feature.id)
            .join(
                CharacterFeatureChoice,
                and_(
                    CharacterFeatureChoice.character_feature_id == CharacterFeature.id,
                    CharacterFeatureChoice.choice_option_id == FeatureChoiceOption.id,
                ),
            )
            .where(CharacterFeature.character_id == character_id, *picked_conditions)
        )

        claims: dict[int, SkillClaim] = {}
        features: dict[int, SimpleNamespace] = {}
        for feature_id, name, source_type, effect_mode in (await self.db.execute(union_all(fixed, picked))).all():
            features[feature_id] = SimpleNamespace(id=feature_id, name=name, source_type=source_type)
            claim = claims.setdefault(feature_id, SkillClaim())
            if effect_mode is not None:
                claim.add(effect_mode)

        key = proficiency_key(proficiency_type, **discriminator)
        # feature_source reads only id/name/source_type, which the namespace carries
        if is_skill:
            return [
                skill_claim_entry(discriminator["skill_id"], feature_source(cast(Feature, feature)), claims[feature_id])
                for feature_id, feature in features.items()
            ]
        return [ProficiencyEntry(key, feature_source(cast(Feature, feature))) for feature in features.values()]

    async def apply(
        self,
        character_id: int,
        proficiency_type: ProficiencyType,
        rows: list[CharacterProficiency],
        *,
        granted: bool,
        others_grant: bool,
        actor_user_id: int | None,
        is_expertise: bool | None = None,
        **discriminator,
    ) -> CharacterProficiency | None:
        """
        Make the GM layer produce the wanted outcome for one proficiency
        and return the GM row that results (``None`` when no row is needed).

        ``granted`` is the outcome the GM wants; ``others_grant`` says whether
        any non-GM source (stored row or feature/feat grant) gives it anyway.
        When they agree no GM row is needed and an existing one is deleted
        (back to whatever the other sources say); otherwise the GM row
        carries the decision — ``GRANT`` when nothing else grants it,
        ``REVOKE`` as a veto over sources that do — and is updated in place
        or inserted. An explicit ``is_expertise`` always needs a GRANT row to
        live on. ``rows`` is what :meth:`get_rows` returned for this proficiency.
        """

        gm_row = next((row for row in rows if row.source_type == ProficiencySourceType.GM), None)

        if granted == others_grant and is_expertise is None:
            if gm_row is not None:
                await self.db.delete(gm_row)
                await self.db.flush()
            return None

        action = ProficiencyAction.GRANT if granted else ProficiencyAction.REVOKE
        expertise = is_expertise if granted else None

        if gm_row is None:
            gm_row = CharacterProficiency(
                character_id=character_id,
                proficiency_type=proficiency_type,
                source_type=ProficiencySourceType.GM,
                **discriminator,
            )
            self.db.add(gm_row)

        gm_row.action = action
        gm_row.actor_user_id = actor_user_id
        gm_row.is_expertise = expertise
        await self.db.flush()
        return gm_row
