"""Character repository: base CRUD plus owner scoping and HP updates."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.character_model import Character
from app.models.class_model import Class


class CharacterRepository(BaseRepository[Character]):
    """
    Repository for the ``Character`` model: inherits the full base CRUD,
    eager-loads the relationships ``CharacterResponse`` serializes, and
    pins ``search`` to ``name`` only.
    """

    def __init__(self, db: AsyncSession):
        """Configure the repository's default load options and search fields."""

        super().__init__(
            Character,
            db,
            default_load_options=[
                selectinload(Character.skill_proficiencies),
                selectinload(Character.character_class).selectinload(Class.saving_throws),
                selectinload(Character.conditions),
            ],
            search_fields=["name"],
        )

    async def update_hp(self, character: Character, current_hp: int, temp_hp: int) -> Character:
        """Set current and temp HP directly. Bounds/validation happen in the service."""

        character.current_hp = current_hp
        character.temp_hp = temp_hp
        await self.db.commit()

        return character

    async def get_by_id_light(self, model_id: int) -> Character | None:
        """
        Fetch a ``Character`` row WITHOUT the eager-loaded collections —
        for sub-domain services that only need the scalar columns.
        """

        result = await self.db.execute(select(Character).where(Character.id == model_id))
        return result.scalar_one_or_none()
