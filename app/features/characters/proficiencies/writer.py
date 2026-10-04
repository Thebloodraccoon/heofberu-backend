"""
Shared writer for auto-granted (non-GM, non-engine) skill proficiency rows.

Character creation and the point-rebuild/late-background flows all write
the same shape: one ``CharacterProficiency`` row per skill id, tagged with
its actual originating source. CLASS_CHOICE/RACE/BACKGROUND rows are
deliberately NOT deduplicated against each other — a skill legitimately
reachable from more than one source is several rows, not a conflict (see
``CharacterProficiency`` for the full resolution algorithm) — only within
the same source's own list, so re-adding an id already in that list never
produces a duplicate row for it.
"""

from collections.abc import Iterable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.models.character.character_proficiency_model import CharacterProficiency


def add_skill_proficiencies(
    db: AsyncSession,
    character_id: int,
    skill_ids: list[int],
    source_type: ProficiencySourceType,
) -> None:
    """Add one ``CharacterProficiency(SKILL)`` row per id in ``skill_ids`` (deduplicated within this call)."""

    for skill_id in dict.fromkeys(skill_ids):
        db.add(
            CharacterProficiency(
                character_id=character_id,
                proficiency_type=ProficiencyType.SKILL,
                skill_id=skill_id,
                source_type=source_type,
                action=ProficiencyAction.GRANT,
                is_expertise=False,
            )
        )


async def delete_skill_proficiencies(
    db: AsyncSession, character_id: int, source_types: Iterable[ProficiencySourceType]
) -> None:
    """Delete the character's SKILL rows of the given sources (no flush/commit; the caller owns the transaction)."""

    await db.execute(
        delete(CharacterProficiency).where(
            CharacterProficiency.character_id == character_id,
            CharacterProficiency.proficiency_type == ProficiencyType.SKILL,
            CharacterProficiency.source_type.in_(list(source_types)),
        )
    )
