"""
Repository backing the GM proficiency panel: upserts/clears the GM layer
of a character's proficiency rows in ``character_proficiencies``.

A GM write never touches another source's rows (class/race/background)
— it only ever creates, updates, or deletes the single ``source_type=GM``
row for one (character, proficiency_type, discriminator). Feature/feat
grants have no rows at all: their proficiencies are computed from the
grant (``characters/grants/effects.py``) and only consulted by
``is_granted``.
See ``CharacterProficiency`` for the full resolution algorithm and the
upsert-and-clear rule this repository implements: writing the OPPOSITE
action of an existing GM row deletes it (clears the override back to
whatever the character's other sources say) rather than piling up rows.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.core.base.repository import _commit_or_rollback
from app.features.characters.grants.effects import GrantEffects, load_character_grant_effects
from app.models.character.character_proficiency_model import CharacterProficiency


def _effect_keys(effects: GrantEffects, proficiency_type: ProficiencyType):
    """The keys a grant's computed effects hold for one proficiency kind."""

    if proficiency_type == ProficiencyType.SKILL:
        return effects.skills.keys()
    if proficiency_type == ProficiencyType.SAVING_THROW:
        return effects.saving_throws
    if proficiency_type == ProficiencyType.ARMOR:
        return effects.armor
    return effects.weapons


def _discriminator_key(proficiency_type: ProficiencyType, discriminator: dict):
    """The same key, built from the ``**discriminator`` the GM service passes."""

    if proficiency_type == ProficiencyType.WEAPON:
        return (discriminator.get("weapon_category"), discriminator.get("item_id"))
    (value,) = discriminator.values()
    return value


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

    async def is_granted(self, character_id: int, proficiency_type: ProficiencyType, **discriminator) -> bool:
        """
        Whether the character currently has the proficiency from any source:
        a GM row decides outright; otherwise any stored row or any
        feature/feat grant's computed effect grants it.
        """

        rows = await self.get_rows(character_id, proficiency_type, **discriminator)

        gm_row = next((row for row in rows if row.source_type == ProficiencySourceType.GM), None)
        if gm_row is not None:
            return gm_row.action == ProficiencyAction.GRANT
        if rows:
            return True

        key = _discriminator_key(proficiency_type, discriminator)
        return any(
            key in _effect_keys(effects, proficiency_type)
            for _, effects in await load_character_grant_effects(self.db, character_id)
        )

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
