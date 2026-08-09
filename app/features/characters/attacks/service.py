"""Character attack CRUD service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.attacks.exceptions import AttackNotFoundException
from app.features.characters.attacks.repository import AttackRepository
from app.features.characters.attacks.schemas import AttackCreate, AttackResponse, AttackUpdate
from app.features.characters.base import CharacterSubDomainService
from app.features.users.schemas import UserResponse
from app.models.attack_model import Attack


class CharacterAttackService(CharacterSubDomainService):
    """
    CRUD for a character's attacks/weapons.

    Access control is enforced against the owning character via the
    inherited ``CharacterSubDomainService`` wiring, but persistence goes
    through :class:`AttackRepository` since attacks are their own table.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.attack_repository = AttackRepository(db)

    async def get_attacks(self, character_id: int, current_user: UserResponse) -> list[AttackResponse]:
        """List all attacks belonging to a character."""

        await self.get_character_for_user(character_id, current_user)

        attacks = await self.attack_repository.get_all_by_character(character_id)
        return [AttackResponse.model_validate(attack) for attack in attacks]

    async def create_attack(self, character_id: int, data: AttackCreate, current_user: UserResponse) -> AttackResponse:
        """Add a new attack/weapon entry to a character."""

        await self.get_character_for_user(character_id, current_user)

        payload = data.model_dump()
        payload["character_id"] = character_id
        attack = await self.attack_repository.create(payload)
        return AttackResponse.model_validate(attack)

    async def update_attack(
        self, character_id: int, attack_id: int, data: AttackUpdate, current_user: UserResponse
    ) -> AttackResponse:
        """Update an existing attack/weapon entry."""

        await self.get_character_for_user(character_id, current_user)

        attack = await self._get_attack_or_404(character_id, attack_id)
        fields = data.model_dump(exclude_unset=True)
        updated_attack = await self.attack_repository.update(attack, fields)
        return AttackResponse.model_validate(updated_attack)

    async def delete_attack(self, character_id: int, attack_id: int, current_user: UserResponse) -> bool:
        """Remove an attack/weapon entry from a character."""

        await self.get_character_for_user(character_id, current_user)

        attack = await self._get_attack_or_404(character_id, attack_id)
        return await self.attack_repository.delete(attack)

    async def _get_attack_or_404(self, character_id: int, attack_id: int) -> Attack:
        """Fetch an attack scoped to the character, or raise ``AttackNotFoundException``."""

        attack = await self.attack_repository.get_by_id_and_character(attack_id, character_id)
        if not attack:
            raise AttackNotFoundException(character_id=character_id, attack_id=attack_id)

        return attack
