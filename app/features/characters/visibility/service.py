"""Public showing of a character: the owner's switch and the anonymous public card."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CharacterPublicVisibility
from app.core.base.transaction import TransactionMixin
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.characters.visibility.repository import CharacterVisibilityRepository
from app.features.characters.visibility.schemas import (
    CharacterVisibilityResponse,
    CharacterVisibilityUpdate,
    PublicAbilityScores,
    PublicCharacterCard,
    PublicItem,
)
from app.features.shared.secrets import strip_gm_blocks
from app.features.users.schemas import UserResponse

_CONCEPT_FIELDS = (
    "id",
    "name",
    "level",
    "class_name",
    "subclass_name",
    "race_name",
    "subrace_name",
    "owner_username",
    "public_visibility",
)


class CharacterVisibilityService(TransactionMixin):
    """
    ``PATCH /characters/{id}/public-visibility`` and ``GET /characters/{id}/public``.

    Only the owner switches visibility: not the campaign GM, not the founder ("hide yes, reveal no" — the founder
    can't make a player's character public). A ``HIDDEN`` character's card is a 404, so its existence doesn't leak.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the visibility repository."""

        self.repository = CharacterVisibilityRepository(db)

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    async def set_visibility(
        self, character_id: int, data: CharacterVisibilityUpdate, current_user: UserResponse
    ) -> CharacterVisibilityResponse:
        """Set the owner's public visibility; anyone else gets 403 (404 when the character doesn't exist)."""

        async with self._atomic():
            row = await self.repository.get_owner_and_visibility(character_id)
            if row is None:
                raise CharacterNotFoundException(character_id=character_id)
            if row.owner_id != current_user.id:
                raise CharacterAccessDeniedException()

            await self.repository.set_visibility(character_id, data.public_visibility)
            # ``CharacterResponse`` carries ``public_visibility``, so the cached sheet is stale now.
            await invalidate_character_cache(character_id, db=self.repository.db)

        return CharacterVisibilityResponse(id=character_id, public_visibility=data.public_visibility)

    async def get_public_card(self, character_id: int) -> PublicCharacterCard:
        """The card at the character's visibility level (404 when it doesn't exist or is ``HIDDEN``)."""

        row = await self.repository.get_card_row(character_id)
        if row is None or row.public_visibility == CharacterPublicVisibility.HIDDEN:
            raise CharacterNotFoundException(character_id=character_id)

        card = PublicCharacterCard(**{field: getattr(row, field) for field in _CONCEPT_FIELDS})
        if row.public_visibility != CharacterPublicVisibility.FULL:
            return card

        card.personality_traits = strip_gm_blocks(row.personality_traits)
        card.ideals = strip_gm_blocks(row.ideals)
        card.bonds = strip_gm_blocks(row.bonds)
        card.flaws = strip_gm_blocks(row.flaws)
        card.backstory = strip_gm_blocks(row.backstory) or ""
        if row.strength_total is not None:
            card.ability_scores = PublicAbilityScores(
                strength=row.strength_total,
                dexterity=row.dexterity_total,
                constitution=row.constitution_total,
                intelligence=row.intelligence_total,
                wisdom=row.wisdom_total,
                charisma=row.charisma_total,
            )
        items = await self.repository.list_items(character_id)
        card.items = [PublicItem(name=name, quantity=quantity) for name, quantity in items]
        card.spells = await self.repository.list_spell_names(character_id)
        return card
