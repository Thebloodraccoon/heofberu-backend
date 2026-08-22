"""ORM model for the GM-controlled maximum level a character may reach."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer

from app.settings import settings


class CharacterMaxLevel(settings.Base):  # type: ignore
    """
    The maximum level a character is allowed to reach (GM-set cap).

    One row per character. A row is seeded at ``max_level=1`` when the
    character is created; a GM can only ever raise it — never lower it,
    and never below the character's current level (enforced by
    ``GmPanelLevelService``). ``CharacterProgressionService.level_up``
    reads this table to decide whether the next level-up is allowed.

    The hard ceiling of 20 matches the ``check_character_level_range``
    constraint on ``characters.level``.
    """

    __tablename__ = "character_max_levels"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    max_level = Column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("max_level >= 1 AND max_level <= 20", name="check_character_max_level_range"),)

    def __repr__(self):
        return f"<CharacterMaxLevel(character_id={self.character_id}, max_level={self.max_level})>"
