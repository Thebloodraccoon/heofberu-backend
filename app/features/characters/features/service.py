"""Character feature service: the read-only feature listing (writes are GM-only, served by the GM panel)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.features.schemas import CharacterFeatureBriefResponse, CharacterFeatureResponse
from app.features.characters.grants.effects import build_chosen_options, get_grant_effects_map
from app.features.users.schemas import UserResponse


class CharacterFeatureService(CharacterSubDomainService):
    """
    Read-only feature listing for a character: every non-feat feature
    grant (progression auto-grants plus GM records). Writes are GM-only
    and live in ``app.features.characters.gm_panel.features``.
    """

    def __init__(self, db: AsyncSession):
        """Create the feature-grant repository alongside the shared character access check."""

        super().__init__(db)
        self.feature_grant_repository = CharacterFeatureRepository(db)

    async def get_features(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatureResponse]:
        """
        List every feature recorded on a character (progression auto-grants
        plus GM records), each with what it actually materialized on the
        character (``effects``) and the player's resolved picks (``choices``).
        """

        await self.get_character_for_user(character_id, current_user)

        grants = await self.feature_grant_repository.get_character_features(character_id)
        effects_by_grant = await get_grant_effects_map(self.repository.db, [grant.id for grant in grants])

        return [
            CharacterFeatureResponse(
                id=grant.id,
                character_id=grant.character_id,
                feature_id=grant.feature_id,
                grant_source=grant.grant_source,
                feature=CharacterFeatureBriefResponse.model_validate(grant.feature),
                effects=effects_by_grant[grant.id],
                choices=build_chosen_options(grant),
            )
            for grant in grants
        ]
