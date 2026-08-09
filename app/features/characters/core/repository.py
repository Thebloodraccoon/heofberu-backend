"""Character repository: base CRUD plus owner scoping and HP updates."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.models.character_model import Character


class CharacterRepository(BaseRepository[Character]):
    """
    Repository for the ``Character`` model itself.

    Inherits the full base CRUD contract unchanged (``get_all``,
    ``get_by_id``, ``get_brief``, ``create``, ``update``, ``delete``,
    ``count``). The previous signature-mismatched overrides are gone:

      - ``get_all()``  ->  base ``get_all(order_by=Character.name,
        limit=None)`` for the GM listing, or ``get_all(filters=
        {"owner_id": ...}, order_by=Character.name, limit=None)`` for the
        player listing (owner scoping via the generic ``filters``).
      - ``get_all_by_owner(owner_id)``  ->  base ``get_all`` with the
        ``owner_id`` filter (method deleted, single call site updated).
      - ``create(data, owner_id)``  ->  the service injects ``owner_id``
        into the payload before calling the base ``create``, mirroring how
        ``created_by_id`` is injected for races/classes/backgrounds.

    Eager-loads every relationship ``CharacterResponse`` always
    serializes, via ``default_load_options`` — this prevents the N+1 the
    previous implementation had on ``skill_proficiencies``,
    ``saving_throw_proficiencies``, ``spell_slots``, and ``attacks``.

    ``search_fields=["name"]`` pins free-text ``search`` (on the
    inherited ``get_all``) to just ``name`` — without this, the base
    class's auto-detection would also search ``traits``, ``backstory``,
    ``notes`` and the other free-text columns on ``Character``, which
    isn't the intended behavior for the listing endpoint's ``search``
    parameter.

    ``update_hp`` stays here: it's a two-column specialized write, not a
    generic ``update`` call.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            Character,
            db,
            default_load_options=[
                selectinload(Character.skill_proficiencies),
                selectinload(Character.saving_throw_proficiencies),
                selectinload(Character.spell_slots),
                selectinload(Character.attacks),
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
        Fetch a ``Character`` row WITHOUT the eager-loaded collections.

        Used by the sub-domain services (features, feats, spells, items,
        conditions, attacks, progression), which only need the scalar
        columns for the access check and their own writes — loading all
        four relationship collections here would cost four queries per
        call for nothing.
        """

        result = await self.db.execute(select(Character).where(Character.id == model_id))
        return result.scalar_one_or_none()
