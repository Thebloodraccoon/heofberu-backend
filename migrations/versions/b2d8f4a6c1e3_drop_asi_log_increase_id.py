"""drop character_asi_choices.ability_score_increase_id

A feat taken at an ASI level is only named in the ASI log now: its ability-score pick (like every
other choice of it) lives in ``character_feature_choices`` and is answered through the grant's
choices, so the log's copy of it goes. Nothing is lost — the pick was always stored on the grant too.

Revision ID: b2d8f4a6c1e3
Revises: a7c3e9b1d5f2
Create Date: 2026-10-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2d8f4a6c1e3"
down_revision: Union[str, None] = "a7c3e9b1d5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_character_asi_choices_ability_score_increase_id", table_name="character_asi_choices")
    op.drop_constraint(
        "character_asi_choices_ability_score_increase_id_fkey", "character_asi_choices", type_="foreignkey"
    )
    op.drop_column("character_asi_choices", "ability_score_increase_id")


def downgrade() -> None:
    op.add_column("character_asi_choices", sa.Column("ability_score_increase_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "character_asi_choices_ability_score_increase_id_fkey",
        "character_asi_choices",
        "feature_ability_score_effects",
        ["ability_score_increase_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_character_asi_choices_ability_score_increase_id", "character_asi_choices", ["ability_score_increase_id"]
    )
