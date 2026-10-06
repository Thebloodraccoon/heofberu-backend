"""
ORM model for a character's stored proficiencies: class/race/background
choices and GM overrides, each row carrying its provenance. Proficiencies
from feature/feat grants are NOT stored here — they are computed on read
from the grant's feature effect tree plus the player's picks
(``app.features.characters.grants.effects``) and merged in by the readers.

A given proficiency can come from several sources at once (e.g. a skill
from both the class AND a feat — both are legitimate, neither is a
duplicate to collapse), except ``source_type=GM`` which is upserted in
place: at most one GM row per (character, proficiency), so it always
reflects the GM's latest decision rather than piling up history.

Resolution algorithm for "does the character currently have proficiency P":
1. Gather every row for (character_id, proficiency_type, discriminator=P)
   plus every feature/feat grant's computed effect for P.
2. If a ``GM`` row with ``action=REVOKE`` exists -> no, full stop. The GM
   veto wins over every other source, including ones still "wanting" to
   grant it (e.g. the class or a feature), since nothing but another GM
   write ever touches a GM row.
3. Else if any source grants it (GM GRANT row, any other row, or a
   feature/feat grant) -> yes.
4. Else -> no.

Every caller of this algorithm runs the same query shape — (character_id,
proficiency_type, one discriminator column) — so indexing is built around
that, not around the individual discriminator columns; see the composite
index below.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import (
    AbilityScore,
    ArmorProficiency,
    ProficiencyAction,
    ProficiencySourceType,
    ProficiencyType,
    WeaponProficiency,
)
from app.models.enums import (
    AbilityScoreType,
    ArmorProficiencyType,
    ProficiencyActionType,
    ProficiencySourceTypeType,
    ProficiencyTypeType,
    WeaponProficiencyType,
)
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character
    from app.models.items.item_model import Item
    from app.models.skill_model import Skill
    from app.models.user_model import User

_DISCRIMINATOR_SHAPE = (
    "(proficiency_type = 'SKILL' AND skill_id IS NOT NULL AND ability IS NULL "
    "AND armor_type IS NULL AND weapon_category IS NULL AND item_id IS NULL)"
    " OR "
    "(proficiency_type = 'SAVING_THROW' AND ability IS NOT NULL AND skill_id IS NULL "
    "AND armor_type IS NULL AND weapon_category IS NULL AND item_id IS NULL)"
    " OR "
    "(proficiency_type = 'ARMOR' AND armor_type IS NOT NULL AND skill_id IS NULL "
    "AND ability IS NULL AND weapon_category IS NULL AND item_id IS NULL)"
    " OR "
    "(proficiency_type = 'WEAPON' AND skill_id IS NULL AND ability IS NULL AND armor_type IS NULL "
    "AND ((weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)))"
)


class CharacterProficiency(Base):
    """
    One provenance row: "character X has/had proficiency P via source S."

    Exactly one of ``skill_id``/``ability``/``armor_type``/(``weapon_category``
    or ``item_id``) is set, matching ``proficiency_type`` (enforced by
    ``ck_character_proficiency_discriminator_shape``). ``actor_user_id`` is
    set only on GM rows.

    Uniqueness is deliberately asymmetric:
    - At most one ``GM`` row per (character, proficiency) — a GM edit is
      current state, not a history entry, so it upserts in place.
    - No uniqueness at all for ``CLASS``/``CLASS_CHOICE``/``RACE``/
      ``BACKGROUND`` — a proficiency legitimately reachable from more than
      one source is several rows, not a conflict. Those
      source types are written wholesale (cleared and rewritten together) by
      character creation / point-rebuild rather than incrementally
      reconciled, so no DB constraint is needed to keep them from
      duplicating in place.
    """

    __tablename__ = "character_proficiencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    # No index=True here: every real query filters (character_id,
    # proficiency_type) together (GM writes, the proficiency read),
    # so the composite index below covers this column too (leftmost-prefix)
    # — a separate single-column index on character_id would be redundant.
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    proficiency_type: Mapped[ProficiencyType] = mapped_column(ProficiencyTypeType)

    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)
    armor_type: Mapped[ArmorProficiency | None] = mapped_column(ArmorProficiencyType)
    weapon_category: Mapped[WeaponProficiency | None] = mapped_column(WeaponProficiencyType)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)

    source_type: Mapped[ProficiencySourceType] = mapped_column(ProficiencySourceTypeType)
    action: Mapped[ProficiencyAction] = mapped_column(ProficiencyActionType, default="GRANT")

    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    is_expertise: Mapped[bool | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    character: Mapped[Character] = relationship(back_populates="proficiencies")
    skill: Mapped[Skill | None] = relationship()
    item: Mapped[Item | None] = relationship()
    actor: Mapped[User | None] = relationship()

    __table_args__ = (
        CheckConstraint(_DISCRIMINATOR_SHAPE, name="ck_character_proficiency_discriminator_shape"),
        # Every read (GM add/remove/expertise-toggle check, the proficiency
        # listing) queries exactly (character_id, proficiency_type, one
        # discriminator column). This composite index resolves the first
        # two columns down to a handful of rows per character+type; the
        # discriminator check on that tiny set is effectively free without
        # needing its own index — see the module docstring.
        Index("ix_character_proficiency_character_type", "character_id", "proficiency_type"),
        # At most one GM row per (character, proficiency) — upserted, not appended.
        Index(
            "uq_character_proficiency_gm_skill",
            "character_id",
            "skill_id",
            unique=True,
            postgresql_where=(source_type == "GM") & (proficiency_type == "SKILL"),
        ),
        Index(
            "uq_character_proficiency_gm_save",
            "character_id",
            "ability",
            unique=True,
            postgresql_where=(source_type == "GM") & (proficiency_type == "SAVING_THROW"),
        ),
        Index(
            "uq_character_proficiency_gm_armor",
            "character_id",
            "armor_type",
            unique=True,
            postgresql_where=(source_type == "GM") & (proficiency_type == "ARMOR"),
        ),
        Index(
            "uq_character_proficiency_gm_weapon_category",
            "character_id",
            "weapon_category",
            unique=True,
            postgresql_where=(source_type == "GM") & (proficiency_type == "WEAPON") & (weapon_category != None),  # noqa: E711
        ),
        Index(
            "uq_character_proficiency_gm_weapon_item",
            "character_id",
            "item_id",
            unique=True,
            postgresql_where=(source_type == "GM") & (proficiency_type == "WEAPON") & (item_id != None),  # noqa: E711
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CharacterProficiency(character_id={self.character_id}, "
            f"proficiency_type='{self.proficiency_type}', source_type='{self.source_type}')>"
        )
