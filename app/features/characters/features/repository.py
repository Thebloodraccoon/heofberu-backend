"""Repository for the feature grants recorded on a character (``character_features``) and their picks."""

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType, GrantSource
from app.core.base.repository import BaseRepository
from app.features.characters.grants.effects import GRANT_CHOICES_LOADS
from app.features.features.crud.repository import feature_summary_loads
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.features.feature_model import Feature

# ``CharacterFeatureBriefResponse.effects_summary`` reads the ``Feature`` ORM
# property of the same name, which touches every fixed-effect relationship and
# the choice-group tree — ``grant.feature`` needs the full engine effect tree
# wherever that response is built.
_WITH_FEATURE_SUMMARY = feature_summary_loads(base=selectinload(CharacterFeature.feature))

_WITH_ANSWERS = [selectinload(CharacterFeature.feature), *GRANT_CHOICES_LOADS]


class CharacterFeatureRepository(BaseRepository[CharacterFeature]):
    """Repository for the features recorded on a character (``character_features``)."""

    def __init__(self, db: AsyncSession):
        """Create the feature-grant repository."""

        super().__init__(CharacterFeature, db)

    async def get_character_features(self, character_id: int) -> list[CharacterFeature]:
        """
        Get every feature grant for a character, EXCLUDING feats.

        A feat is a ``character_features`` row whose ``feature.source_type
        == FEAT`` too (a feat IS a Feature), but it is surfaced through
        ``GET /characters/{id}/feats`` — excluding it here keeps the same
        grant from appearing twice in the character sheet.
        """

        result = await self.db.execute(
            select(CharacterFeature)
            .join(Feature, Feature.id == CharacterFeature.feature_id)
            .options(*_WITH_FEATURE_SUMMARY, *GRANT_CHOICES_LOADS)
            .where(CharacterFeature.character_id == character_id, Feature.source_type != FeatureSourceType.FEAT)
        )
        return list(result.scalars().unique().all())

    async def get_character_feature_by_id(
        self, character_id: int, character_feature_id: int
    ) -> CharacterFeature | None:
        """Fetch a single feature grant by its own id, scoped to the character."""

        result = await self.db.execute(
            select(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .where(
                CharacterFeature.id == character_feature_id,
                CharacterFeature.character_id == character_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_character_feature_by_feature_id(self, character_id: int, feature_id: int) -> CharacterFeature | None:
        """Fetch a character's grant for a specific reference feature, if any (used for duplicate checks)."""

        result = await self.db.execute(
            select(CharacterFeature).where(
                CharacterFeature.character_id == character_id,
                CharacterFeature.feature_id == feature_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_character_feature(
        self,
        character_id: int,
        feature_id: int,
        *,
        grant_source: GrantSource = GrantSource.GM,
        commit: bool = True,
    ) -> CharacterFeature:
        """
        Record a reference feature on a character.

        ``grant_source`` defaults to ``GM`` (the manual-grant path;
        ``sync_progression_features`` writes ``AUTO``) so a later sync never
        mistakes a GM's grant for a stale auto-grant and revokes it.
        ``commit=False`` flushes instead, for callers inside their own
        transaction.
        """

        grant = CharacterFeature(
            character_id=character_id,
            feature_id=feature_id,
            grant_source=grant_source,
        )

        self.db.add(grant)
        await self.commit_or_flush(commit=commit)

        result = await self.db.execute(
            select(CharacterFeature).options(*_WITH_FEATURE_SUMMARY).where(CharacterFeature.id == grant.id)
        )
        return result.scalar_one()

    async def remove_character_feature(self, grant: CharacterFeature, *, commit: bool = True) -> bool:
        """Remove a feature grant from a character (``commit=False`` flushes, for callers inside their own transaction)."""

        await self.db.delete(grant)
        await self.commit_or_flush(commit=commit)
        return True

    async def get_grant(
        self, character_id: int, grant_id: int, *, for_update: bool = False, with_answers: bool = False
    ) -> CharacterFeature | None:
        """
        Fetch a grant scoped to the character. ``for_update`` row-locks it;
        ``with_answers`` eager-loads ``feature`` and the stored picks.
        """

        query = select(CharacterFeature).where(
            CharacterFeature.id == grant_id,
            CharacterFeature.character_id == character_id,
        )
        if for_update:
            query = query.with_for_update()
        if with_answers:
            query = query.options(*_WITH_ANSWERS)

        result = await self.db.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_grants_with_choices(self, character_id: int) -> list[CharacterFeature]:
        """The character's grants whose feature has choice groups (``Feature.has_choices``)."""

        result = await self.db.execute(
            select(CharacterFeature)
            .join(Feature, Feature.id == CharacterFeature.feature_id)
            .where(CharacterFeature.character_id == character_id, Feature.has_choices.is_(True))
        )
        return list(result.scalars().unique().all())

    async def get_answered_grants(self, character_id: int) -> list[CharacterFeature]:
        """The character's grants with at least one stored pick, ``feature`` and picks eager-loaded."""

        result = await self.db.execute(
            select(CharacterFeature)
            .where(CharacterFeature.character_id == character_id, CharacterFeature.choices.any())
            .options(*_WITH_ANSWERS)
        )
        return list(result.unique().scalars().all())

    async def filter_features_with_choices(self, feature_ids: Iterable[int]) -> set[int]:
        """The subset of ``feature_ids`` whose feature has choice groups."""

        ids = set(feature_ids)
        if not ids:
            return ids

        result = await self.db.execute(select(Feature.id).where(Feature.id.in_(ids), Feature.has_choices.is_(True)))
        return set(result.scalars().all())

    async def get_choices(self, grant_ids: Iterable[int]) -> list[CharacterFeatureChoice]:
        """Stored picks of the given grants."""

        ids = list(grant_ids)
        if not ids:
            return []

        result = await self.db.execute(
            select(CharacterFeatureChoice).where(CharacterFeatureChoice.character_feature_id.in_(ids))
        )
        return list(result.scalars().unique().all())

    async def replace_choices(
        self, grant_id: int, option_ids_by_group: dict[int, list[int]]
    ) -> list[CharacterFeatureChoice]:
        """
        Replace the grant's stored picks of every group in ``option_ids_by_group``
        (flush only, never commits); return the new pick rows.
        """

        await self.db.execute(
            delete(CharacterFeatureChoice).where(
                CharacterFeatureChoice.character_feature_id == grant_id,
                CharacterFeatureChoice.choice_group_id.in_(list(option_ids_by_group)),
            )
        )
        await self.db.flush()

        new_choices = [
            CharacterFeatureChoice(character_feature_id=grant_id, choice_group_id=group_id, choice_option_id=option_id)
            for group_id, option_ids in option_ids_by_group.items()
            for option_id in option_ids
        ]
        self.db.add_all(new_choices)
        await self.db.flush()
        return new_choices
