"""open spell picks: spell-effect filters + the spell a player picked

* ``feature_spell_grant_effects`` gets the filters of an open ("any spell") effect: ``class_ids``
  (INTEGER[]), ``min_level`` / ``max_level`` (``spell_level``), ``castable_only``, ``schools``
  (``spell_school[]``) and ``ritual_only``. Empty / NULL / false = no restriction.
* ``character_feature_choices.picked_spell_id`` — the spell a player named for an open option. The
  "nothing named" partial unique index now also requires ``picked_spell_id IS NULL``, and a third
  partial unique index covers picks naming a spell.

The downgrade deletes picks that name a spell (the old schema can't hold them).

Revision ID: a7c3e9b1d5f2
Revises: e4b7d1f9a3c6
Create Date: 2026-10-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7c3e9b1d5f2"
down_revision: Union[str, None] = "e4b7d1f9a3c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SPELL_LEVEL = postgresql.ENUM(name="spell_level", create_type=False)
_SPELL_SCHOOL = postgresql.ENUM(name="spell_school", create_type=False)


def upgrade() -> None:
    op.add_column(
        "feature_spell_grant_effects",
        sa.Column("class_ids", postgresql.ARRAY(sa.Integer()), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("feature_spell_grant_effects", sa.Column("min_level", _SPELL_LEVEL, nullable=True))
    op.add_column("feature_spell_grant_effects", sa.Column("max_level", _SPELL_LEVEL, nullable=True))
    op.add_column(
        "feature_spell_grant_effects",
        sa.Column("castable_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "feature_spell_grant_effects",
        sa.Column("schools", postgresql.ARRAY(_SPELL_SCHOOL), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "feature_spell_grant_effects",
        sa.Column("ritual_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column("character_feature_choices", sa.Column("picked_spell_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "character_feature_choices_picked_spell_id_fkey",
        "character_feature_choices",
        "spells",
        ["picked_spell_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_character_feature_choices_picked_spell_id", "character_feature_choices", ["picked_spell_id"])
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NULL AND picked_spell_id IS NULL"),
    )
    op.create_index(
        "uq_character_feature_choice_option_spell",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id", "picked_spell_id"],
        unique=True,
        postgresql_where=sa.text("picked_spell_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM character_feature_choices WHERE picked_spell_id IS NOT NULL")
    op.drop_index("uq_character_feature_choice_option_spell", table_name="character_feature_choices")
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NULL"),
    )
    op.drop_index("ix_character_feature_choices_picked_spell_id", table_name="character_feature_choices")
    op.drop_constraint(
        "character_feature_choices_picked_spell_id_fkey", "character_feature_choices", type_="foreignkey"
    )
    op.drop_column("character_feature_choices", "picked_spell_id")

    for column in ("ritual_only", "schools", "castable_only", "max_level", "min_level", "class_ids"):
        op.drop_column("feature_spell_grant_effects", column)
