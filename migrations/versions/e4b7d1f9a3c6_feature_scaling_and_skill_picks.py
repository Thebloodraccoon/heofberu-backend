"""feature scaling line + open skill picks + skill-effect mode

* ``features.scaling`` (JSONB, ``{"label", "steps": [{"level", "value"}]}``) — the one line of a
  feature that grows with the character's level (Song of Rest: 1d6 -> 1d8 at 9 -> ...).
* ``feature_skill_proficiency_effects.mode`` (VARCHAR, ``SkillEffectMode`` member name) replaces
  ``grants_expertise``: ``true -> PROFICIENCY_AND_EXPERTISE``, ``false -> PROFICIENCY`` (same behavior).
* ``character_feature_choices.picked_skill_id`` — the skill a player named for an open ("any skill")
  option. The unique ``(character_feature_id, choice_group_id, choice_option_id)`` constraint becomes
  two partial unique indexes (without / with a named skill), and ``character_feature_id`` gets its own
  index back (the partial indexes can't serve a plain ``WHERE character_feature_id IN (...)``).

The downgrade deletes picks that name a skill (the old schema can't hold them) and folds
``EXPERTISE`` into ``grants_expertise=true`` and ``UPGRADE`` into ``false`` — lossy: the old schema has
no "expertise only" effect, so an ``EXPERTISE`` effect comes back as proficiency + expertise, and an
``UPGRADE`` one as plain proficiency.

Revision ID: e4b7d1f9a3c6
Revises: c8e2a4f6d1b9
Create Date: 2026-10-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e4b7d1f9a3c6"
down_revision: Union[str, None] = "c8e2a4f6d1b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("features", sa.Column("scaling", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column(
        "feature_skill_proficiency_effects",
        sa.Column("mode", sa.String(length=30), nullable=False, server_default="PROFICIENCY"),
    )
    op.execute("UPDATE feature_skill_proficiency_effects SET mode = 'PROFICIENCY_AND_EXPERTISE' WHERE grants_expertise")
    op.drop_column("feature_skill_proficiency_effects", "grants_expertise")

    op.add_column("character_feature_choices", sa.Column("picked_skill_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "character_feature_choices_picked_skill_id_fkey",
        "character_feature_choices",
        "skills",
        ["picked_skill_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_character_feature_choices_picked_skill_id", "character_feature_choices", ["picked_skill_id"])
    op.create_index(
        "ix_character_feature_choices_character_feature_id", "character_feature_choices", ["character_feature_id"]
    )
    op.drop_constraint("uq_character_feature_choice_option", "character_feature_choices", type_="unique")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NULL"),
    )
    op.create_index(
        "uq_character_feature_choice_option_skill",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id", "picked_skill_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM character_feature_choices WHERE picked_skill_id IS NOT NULL")
    op.drop_index("uq_character_feature_choice_option_skill", table_name="character_feature_choices")
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_unique_constraint(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
    )
    op.drop_index("ix_character_feature_choices_character_feature_id", table_name="character_feature_choices")
    op.drop_index("ix_character_feature_choices_picked_skill_id", table_name="character_feature_choices")
    op.drop_constraint(
        "character_feature_choices_picked_skill_id_fkey", "character_feature_choices", type_="foreignkey"
    )
    op.drop_column("character_feature_choices", "picked_skill_id")

    op.add_column(
        "feature_skill_proficiency_effects",
        sa.Column("grants_expertise", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE feature_skill_proficiency_effects SET grants_expertise = true "
        "WHERE mode IN ('PROFICIENCY_AND_EXPERTISE', 'EXPERTISE')"
    )
    op.drop_column("feature_skill_proficiency_effects", "mode")

    op.drop_column("features", "scaling")
