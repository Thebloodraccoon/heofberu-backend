"""Add subraces; drop race-owned starting equipment

Adds the new ``subraces`` reference table (race lineage, e.g. Elf ->
High Elf / Wood Elf / Drow) with per-subrace ability bonuses
(``subrace_ability_bonuses``), plus:

  - ``features.subrace_id`` — subrace-owned features (``source_type=SUBRACE``);
  - ``characters.subrace_id`` — the subrace a character belongs to.

Races no longer own starting equipment, so the unused ``source_items.race_id``
column is dropped.

Revision ID: 8a4c5d6e7f8a
Revises: e7f8a9b0c1d2
Create Date: 2026-08-11 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8a4c5d6e7f8a"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()

    # Extend the feature_source_type enum with SUBRACE (Postgres supports
    # ADD VALUE only once; guard against re-runs).
    has_subrace = bind.execute(
        sa.text("SELECT 1 FROM pg_enum WHERE enumlabel = 'SUBRACE' AND enumtypid = 'feature_source_type'::regtype")
    ).first()
    if has_subrace is None:
        op.execute("ALTER TYPE feature_source_type ADD VALUE 'SUBRACE'")

    # Races no longer own starting equipment — drop the unused column.
    source_item_cols = {c["name"] for c in inspect(bind).get_columns("source_items")}
    if "race_id" in source_item_cols:
        op.drop_index(op.f("ix_source_items_race_id"), table_name="source_items")
        op.drop_constraint("source_items_race_id_fkey", "source_items", type_="foreignkey")
        op.drop_column("source_items", "race_id")

    op.create_table(
        "subraces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("race_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_homebrew", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["race_id"], ["races.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("race_id", "name", name="uq_subrace_race_id_name"),
    )
    op.create_index(op.f("ix_subraces_created_by_id"), "subraces", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_subraces_name"), "subraces", ["name"], unique=False)
    op.create_index(op.f("ix_subraces_race_id"), "subraces", ["race_id"], unique=False)

    op.create_table(
        "subrace_ability_bonuses",
        sa.Column("subrace_id", sa.Integer(), nullable=False),
        sa.Column(
            "ability",
            postgresql.ENUM("STR", "DEX", "CON", "INT", "WIS", "CHA", name="ability_score", create_type=False),
            nullable=False,
        ),
        sa.Column("bonus", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["subrace_id"], ["subraces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("subrace_id", "ability"),
    )

    op.add_column("features", sa.Column("subrace_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_features_subrace_id"), "features", ["subrace_id"], unique=False)
    op.create_foreign_key(
        "fk_features_subrace_id_subraces", "features", "subraces", ["subrace_id"], ["id"], ondelete="CASCADE"
    )

    op.add_column("characters", sa.Column("subrace_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_characters_subrace_id"), "characters", ["subrace_id"], unique=False)
    op.create_foreign_key(
        "fk_characters_subrace_id_subraces", "characters", "subraces", ["subrace_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("fk_characters_subrace_id_subraces", "characters", type_="foreignkey")
    op.drop_index(op.f("ix_characters_subrace_id"), table_name="characters")
    op.drop_column("characters", "subrace_id")

    op.drop_constraint("fk_features_subrace_id_subraces", "features", type_="foreignkey")
    op.drop_index(op.f("ix_features_subrace_id"), table_name="features")
    op.drop_column("features", "subrace_id")

    op.drop_table("subrace_ability_bonuses")
    op.drop_table("subraces")

    bind = op.get_bind()
    source_item_cols = {c["name"] for c in inspect(bind).get_columns("source_items")}
    if "race_id" not in source_item_cols:
        op.add_column("source_items", sa.Column("race_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "source_items_race_id_fkey", "source_items", "races", ["race_id"], ["id"], ondelete="CASCADE"
        )
        op.create_index(op.f("ix_source_items_race_id"), "source_items", ["race_id"], unique=False)

    # Postgres 11+ allows DROP VALUE only when the value is unused (and before
    # 12 it is not supported at all), so guard failure gracefully.
    op.execute("DELETE FROM pg_enum WHERE enumlabel = 'SUBRACE' AND enumtypid = 'feature_source_type'::regtype")
