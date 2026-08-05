"""Character attack CRUD service."""

from sqlalchemy.orm import Session

from app.features.characters.access import get_character_for_user
from app.features.characters.attacks.exceptions import AttackNotFoundException
from app.features.characters.attacks.repository import AttackRepository
from app.features.characters.attacks.schemas import AttackCreate, AttackResponse, AttackUpdate
from app.features.characters.core.repository import CharacterRepository
from app.features.users.schemas import UserResponse
from app.models.attack_model import Attack


class CharacterAttackService:
    """
    CRUD for a character's attacks/weapons.

    Access control is still enforced against the owning character (via
    :class:`CharacterRepository`), but persistence goes through
    :class:`AttackRepository` since attacks are their own table.
    """

    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
        self.attack_repository = AttackRepository(db)

    def get_attacks(self, character_id: int, current_user: UserResponse) -> list[AttackResponse]:
        """List all attacks belonging to a character."""

        get_character_for_user(self.repository, character_id, current_user)

        attacks = self.attack_repository.get_all_by_character(character_id)
        return [AttackResponse.model_validate(attack) for attack in attacks]

    def create_attack(self, character_id: int, data: AttackCreate, current_user: UserResponse) -> AttackResponse:
        """Add a new attack/weapon entry to a character."""

        get_character_for_user(self.repository, character_id, current_user)

        attack = self.attack_repository.create(data.model_dump(), character_id)
        return AttackResponse.model_validate(attack)

    def update_attack(
        self, character_id: int, attack_id: int, data: AttackUpdate, current_user: UserResponse
    ) -> AttackResponse:
        """Update an existing attack/weapon entry."""

        get_character_for_user(self.repository, character_id, current_user)

        attack = self._get_attack_or_404(character_id, attack_id)
        fields = data.model_dump(exclude_unset=True)
        updated_attack = self.attack_repository.update(attack, fields)
        return AttackResponse.model_validate(updated_attack)

    def delete_attack(self, character_id: int, attack_id: int, current_user: UserResponse) -> bool:
        """Remove an attack/weapon entry from a character."""

        get_character_for_user(self.repository, character_id, current_user)

        attack = self._get_attack_or_404(character_id, attack_id)
        return self.attack_repository.delete(attack)

    def _get_attack_or_404(self, character_id: int, attack_id: int) -> Attack:
        """Fetch an attack scoped to the character, or raise ``AttackNotFoundException``."""

        attack = self.attack_repository.get_by_id_and_character(attack_id, character_id)
        if not attack:
            raise AttackNotFoundException(character_id=character_id, attack_id=attack_id)

        return attack
