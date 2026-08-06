"""Attack repository: character-scoped attack CRUD."""

from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.attack_model import Attack


class AttackRepository(BaseRepository[Attack]):
    """
    Repository for the ``Attack`` model. Used by the attacks sub-domain
    (CRUD).

    Inherits the base ``create`` unchanged — the service injects
    ``character_id`` into the create payload before calling it, mirroring
    how ``owner_id`` is injected for characters and ``created_by_id`` for
    races/classes/backgrounds (the old ``create(data, character_id)``
    signature override is gone).
    """

    def __init__(self, db: Session):
        super().__init__(Attack, db)

    def get_all_by_character(self, character_id: int) -> list[Attack]:
        """List a character's attacks, ordered by name."""
        return self.db.query(Attack).filter(Attack.character_id == character_id).order_by(Attack.name).all()

    def get_by_id_and_character(self, attack_id: int, character_id: int) -> Attack | None:
        """Fetch an attack scoped to a character, or None if not present."""
        return self.db.query(Attack).filter(Attack.id == attack_id, Attack.character_id == character_id).first()
