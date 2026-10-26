"""open ability-score / saving-throw picks

* ``feature_ability_score_effects.ability`` and ``feature_saving_throw_effects.ability`` become nullable:
  NULL is an open ("any ability" / "any saving throw") effect, choice options only — a fixed row still
  needs its ability (``ck_feature_ability_score_fixed_requires_ability`` /
  ``ck_feature_saving_throw_fixed_requires_ability``).
* ``character_feature_choices.picked_ability`` — the ability a player named for an open option (one
  column for both effect types: a group carries one effect type). The "nothing named" partial unique
  index now also requires ``picked_ability IS NULL``, and a fourth one covers the named ability.

The downgrade deletes picks that name an ability and the open effect rows (the old schema can't hold
them) — an option left without effects stays, empty.

Revision ID: f3a9c2e7b4d1
Revises: c5e1a9d3f7b2
Create Date: 2026-10-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f3a9c2e7b4d1"
down_revision: Union[str, None] = "c5e1a9d3f7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ABILITY_SCORE = postgresql.ENUM(name="ability_score", create_type=False)


def upgrade() -> None:
    op.alter_column("feature_ability_score_effects", "ability", nullable=True)
    op.create_check_constraint(
        "ck_feature_ability_score_fixed_requires_ability",
        "feature_ability_score_effects",
        "feature_id IS NULL OR ability IS NOT NULL",
    )
    op.alter_column("feature_saving_throw_effects", "ability", nullable=True)
    op.create_check_constraint(
        "ck_feature_saving_throw_fixed_requires_ability",
        "feature_saving_throw_effects",
        "feature_id IS NULL OR ability IS NOT NULL",
    )

    op.add_column("character_feature_choices", sa.Column("picked_ability", _ABILITY_SCORE, nullable=True))
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NULL AND picked_spell_id IS NULL AND picked_ability IS NULL"),
    )
    op.create_index(
        "uq_character_feature_choice_option_ability",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id", "picked_ability"],
        unique=True,
        postgresql_where=sa.text("picked_ability IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM character_feature_choices WHERE picked_ability IS NOT NULL")
    op.drop_index("uq_character_feature_choice_option_ability", table_name="character_feature_choices")
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NULL AND picked_spell_id IS NULL"),
    )
    op.drop_column("character_feature_choices", "picked_ability")

    op.execute("DELETE FROM feature_saving_throw_effects WHERE ability IS NULL")
    op.drop_constraint("ck_feature_saving_throw_fixed_requires_ability", "feature_saving_throw_effects", type_="check")
    op.alter_column("feature_saving_throw_effects", "ability", nullable=False)
    op.execute("DELETE FROM feature_ability_score_effects WHERE ability IS NULL")
    op.drop_constraint(
        "ck_feature_ability_score_fixed_requires_ability", "feature_ability_score_effects", type_="check"
    )
    op.alter_column("feature_ability_score_effects", "ability", nullable=False)
