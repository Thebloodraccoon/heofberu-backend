"""Character repository: base CRUD plus owner scoping and HP updates."""

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models.character_model import Character


class CharacterRepository(BaseRepository[Character]):
    """
    Repository for the ``Character`` model itself.

    Owns only the character record's own CRUD/HP fields. Every other
    sub-domain table that used to live here has its own repository:
    ``CharacterProficiencyRepository`` (skills/saving throws),
    ``CharacterSpellRepository`` (spell slots/known spells),
    ``CharacterFeatRepository`` (feat grants), and
    ``CharacterAbilityScoreCacheRepository`` (the effective-scores
    cache). Every character sub-service still depends on this
    repository too, since it's the one that ``get_character_for_user``
    (access control) is checked against.

    Eager-loads every relationship ``CharacterResponse`` always
    serializes, via ``default_load_options`` — this used to be missing
    entirely, which meant ``GET /characters`` and ``GET /characters/{id}``
    both N+1'd on ``skill_proficiencies``, ``saving_throw_proficiencies``,
    ``spell_slots``, and ``attacks``.
    """

    def __init__(self, db: Session):
        super().__init__(
            Character,
            db,
            default_load_options=[
                selectinload(Character.skill_proficiencies),
                selectinload(Character.saving_throw_proficiencies),
                selectinload(Character.spell_slots),
                selectinload(Character.attacks),
            ],
        )

    def get_all(self) -> list[Character]:  # type: ignore[override]
        """
        Get all characters, ordered by name. GM-only use case.

        Overrides base pagination-based get_all. Still applies
        ``default_load_options`` via ``.options(...)`` since this bypasses
        the base implementation entirely.
        """

        return self.db.query(Character).options(*self._default_load_options).order_by(Character.name).all()

    def get_all_by_owner(self, owner_id: int) -> list[Character]:
        """Get characters owned by a specific user. Player use case."""

        return (
            self.db.query(Character)
            .options(*self._default_load_options)
            .filter(Character.owner_id == owner_id)
            .order_by(Character.name)
            .all()
        )

    def create(self, character_data: dict, owner_id: int) -> Character:  # type: ignore[override]
        """Create a character for a given owner (overrides base create signature)."""

        character = Character(**character_data, owner_id=owner_id)
        self.db.add(character)
        self.db.commit()
        self.db.refresh(character)

        return character

    def update_hp(self, character: Character, current_hp: int, temp_hp: int) -> Character:
        """Set current and temp HP directly. Bounds/validation happen in the service."""

        character.current_hp = current_hp
        character.temp_hp = temp_hp
        self.db.commit()
        self.db.refresh(character)

        return character
