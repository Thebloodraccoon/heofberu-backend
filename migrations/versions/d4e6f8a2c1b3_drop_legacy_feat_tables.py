"""drop legacy feat tables (features-only cleanup)

Revision ID: d4e6f8a2c1b3
Revises: c8f4e2a6b9d3
Create Date: 2026-09-09 00:00:00.000000

The transition to "features-only" is complete: feats ARE ``features`` rows
(``source_type = FEAT``) and character feat grants are ``character_features``
rows. The pre-engine ``feats`` / ``feat_ability_score_increases`` /
``character_feats`` tables are now dead — no ORM model maps them and no code
reads or writes them (migration ``c8f4e2a6b9d3`` backfilled catalog and
grants into the engine tables). This removes them from the schema, along with
the exclusive ``character_feat_source`` enum type.

Data note: contents are unrecoverable (the mirror/backfill in
``c8f4e2a6b9d3`` is the only copy) — the downgrade recreates the tables
empty, best-effort, mirroring the column drift applied across history
(dropped ``created_by_id``/``is_homebrew``, added ``min_level``,
``character_feats.source_type`` and its ``uq_character_feat`` constraint).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e6f8a2c1b3"
down_revision: Union[str, None] = "c8f4e2a6b9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ``ability_score`` is a shared enum (still used by races/subraces/features) —
# only referenced with ``create_type=False``, never recreated.
ability_score_enum = postgresql.ENUM(
    "STR",
    "DEX",
    "CON",
    "INT",
    "WIS",
    "CHA",
    name="ability_score",
    create_type=False,
)
character_feat_source_enum = postgresql.ENUM(
    "GM",
    "ORIGIN",
    "ASI",
    name="character_feat_source",
    create_type=False,
)


def upgrade() -> None:
    """Drop the three legacy feat tables and the ``character_feat_source`` enum type."""

    op.drop_table("character_feats")
    op.drop_table("feat_ability_score_increases")
    op.drop_table("feats")
    character_feat_source_enum.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Recreate the legacy tables (empty) and the enum type — best-effort."""

    character_feat_source_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "feats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("prerequisite_ability", ability_score_enum, nullable=True),
        sa.Column("prerequisite_minimum_score", sa.Integer(), nullable=True),
        sa.Column("prerequisite_description", sa.Text(), nullable=False),
        sa.Column("min_level", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feats_name"), "feats", ["name"], unique=True)

    op.create_table(
        "feat_ability_score_increases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feat_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["feat_id"], ["feats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feat_ability_score_increases_feat_id"), "feat_ability_score_increases", ["feat_id"], unique=False
    )

    op.create_table(
        "character_feats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("feat_id", sa.Integer(), nullable=False),
        sa.Column("ability_score_increase_id", sa.Integer(), nullable=True),
        sa.Column("source_type", character_feat_source_enum, nullable=False, server_default=sa.text("'GM'")),
        sa.ForeignKeyConstraint(
            ["ability_score_increase_id"], ["feat_ability_score_increases.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feat_id"], ["feats.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_character_feats_ability_score_increase_id"),
        "character_feats",
        ["ability_score_increase_id"],
        unique=False,
    )
    op.create_index(op.f("ix_character_feats_character_id"), "character_feats", ["character_id"], unique=False)
    op.create_index(op.f("ix_character_feats_feat_id"), "character_feats", ["feat_id"], unique=False)
    op.create_unique_constraint("uq_character_feat", "character_feats", ["character_id", "feat_id"])