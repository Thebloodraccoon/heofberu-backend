"""Row-level lock on a character, shared by writes whose check-then-act must not interleave."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character.character_model import Character


async def lock_character(db: AsyncSession, character_id: int) -> None:
    """
    ``SELECT ... FOR UPDATE`` the character's row until the transaction ends.

    Call it first inside the transaction that validates against current
    state (a cap, a count, a floor) and then writes, so concurrent writers of
    the same character queue up instead of both passing the check.
    """

    await db.execute(select(Character.id).where(Character.id == character_id).with_for_update())
