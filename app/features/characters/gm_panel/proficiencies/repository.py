"""
Repository backing the GM proficiency panel: upserts/clears the GM layer
of a character's proficiency rows in ``character_proficiencies``.

A GM write never touches another source's rows (class/race/background/
feature) — it only ever creates, updates, or deletes the single
``source_type=GM`` row for one (character, proficiency_type, discriminator).
See ``CharacterProficiency`` for the full resolution algorithm and the
upsert-and-clear rule this repository implements: writing the OPPOSITE
action of an existing GM row deletes it (clears the override back to
whatever the character's other sources say) rather than piling up rows.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.core.base.repository import _commit_or_rollback
from app.models.character.character_proficiency_model import CharacterProficiency


class CharacterProficiencyGmRepository:
    """Owns the GM layer of ``character_proficiencies`` (all proficiency kinds)."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing proficiency rows."""

        self.db = db

    async def get_rows(
        self, character_id: int, proficiency_type: ProficiencyType, **discriminator
    ) -> list[CharacterProficiency]:
        """Every row (any source) for one (character, proficiency) — the resolution algorithm's input."""

        conditions = [
            CharacterProficiency.character_id == character_id,
            CharacterProficiency.proficiency_type == proficiency_type,
        ]
        for column, value in discriminator.items():
            conditions.append(getattr(CharacterProficiency, column) == value)

        result = await self.db.execute(select(CharacterProficiency).where(*conditions))
        return list(result.scalars().unique().all())

    async def resolve(
        self, character_id: int, proficiency_type: ProficiencyType, **discriminator
    ) -> CharacterProficiency | None:
        """
        Resolve current effective state for one (character, proficiency):
        a GM row wins outright (``REVOKE`` -> None, ``GRANT`` -> itself);
        otherwise any row means granted (preferring one with
        ``is_expertise`` set, for skills); no rows -> None.
        """

        rows = await self.get_rows(character_id, proficiency_type, **discriminator)

        gm_row = next((row for row in rows if row.source_type == ProficiencySourceType.GM), None)
        if gm_row is not None:
            return gm_row if gm_row.action == ProficiencyAction.GRANT else None

        if not rows:
            return None

        return next((row for row in rows if row.is_expertise), rows[0])

    async def set_override(
        self,
        character_id: int,
        proficiency_type: ProficiencyType,
        action: ProficiencyAction,
        actor_user_id: int | None,
        *,
        is_expertise: bool | None = None,
        **discriminator,
    ) -> None:
        """
        Upsert-and-clear the GM row for one (character, proficiency).

        An existing GM row with the OPPOSITE action is deleted (the GM
        changed their mind — back to whatever other sources say). An
        existing GM row with the SAME action is updated in place (actor,
        ``is_expertise``). No existing GM row -> a new one is inserted.
        """

        rows = await self.get_rows(character_id, proficiency_type, **discriminator)
        existing = next((row for row in rows if row.source_type == ProficiencySourceType.GM), None)

        if existing is not None:
            if existing.action != action:
                await self.db.delete(existing)
            else:
                existing.actor_user_id = actor_user_id
                if is_expertise is not None:
                    existing.is_expertise = is_expertise
            await _commit_or_rollback(self.db)
            return

        row = CharacterProficiency(
            character_id=character_id,
            proficiency_type=proficiency_type,
            source_type=ProficiencySourceType.GM,
            action=action,
            actor_user_id=actor_user_id,
            is_expertise=is_expertise,
            **discriminator,
        )
        self.db.add(row)
        await _commit_or_rollback(self.db)
