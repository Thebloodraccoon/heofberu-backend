"""Character feat service: the read-only feat listing (writes are GM-only, served by the GM panel)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.feats.repository import CharacterFeatRepository, to_character_feat_response
from app.features.characters.feats.schemas import CharacterFeatResponse
from app.features.characters.grants.effects import get_grant_effects_map
from app.features.users.schemas import UserResponse


class CharacterFeatService(CharacterSubDomainService):
    """
    Read-only feat listing for a character: every feat grant (level-up
    ASI choices and GM grants alike). Writes (grant/update ASI/revoke) are
    GM-only and live in ``app.features.characters.gm_panel.feats``.
    """

    def __init__(self, db: AsyncSession):
        """Create the feat-grant repository alongside the shared character access check."""

        super().__init__(db)
        self.feat_grant_repository = CharacterFeatRepository(db)

    async def get_feats(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatResponse]:
        """
        List every feat granted to a character (level-up choices and GM
        grants alike), each with what it gives the character (``effects``)
        and the player's resolved picks (``choices``).
        """

        await self.get_character_for_user(character_id, current_user)

        grants = await self.feat_grant_repository.get_character_feats(character_id)
        effects_by_grant = await get_grant_effects_map(self.repository.db, grants)

        return [to_character_feat_response(grant, effects_by_grant[grant.id]) for grant in grants]
