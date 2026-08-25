"""normalize character_asi_choices: child increases table + applied_to_base flag

Revision ID: b8e2f4a6c9d1
Revises: f9c6d8e2b4a7
Create Date: 2026-08-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8e2f4a6c9d1"
down_revision: Union[str, None] = "f9c6d8e2b4a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Child table holding the counted increments of each ASI choice
    #    (replaces the untyped `increases` JSONB column).
    op.create_table(
        "character_asi_choice_increases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_asi_choice_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["character_asi_choice_id"],
            ["character_asi_choices.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_asi_choice_id", "ability", name="uq_character_asi_inc_ability"),
    )
    op.create_index(
        op.f("ix_character_asi_choice_increases_character_asi_choice_id"),
        "character_asi_choice_increases",
        ["character_asi_choice_id"],
        unique=False,
    )

    # 2. Grandfather flag: every EXISTING choice had its points applied
    #    straight onto the base ability columns by the old code paths
    #    (level-up ASI bumps and GM ±adjustments), so all of them must be
    #    excluded from the calculator to avoid double counting. The column
    #    is added with a TRUE default so every existing row flips to True,
    #    then the default is switched to FALSE — matching the model — for
    #    all rows written from now on.
    op.add_column(
        "character_asi_choices",
        sa.Column("applied_to_base", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column(
        "character_asi_choices",
        "applied_to_base",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
    )

    # 3. Expand the legacy JSONB payloads into typed child rows so the
    #    audit data survives the (later) column drop; the rows stay
    #    grandfathered via the flag above.
    op.execute(
        """
        INSERT INTO character_asi_choice_increases (character_asi_choice_id, ability, amount)
        SELECT c.id, (entry->>'ability')::ability_score, (entry->>'amount')::integer
        FROM character_asi_choices c,
             jsonb_array_elements(c.increases) AS entry
        WHERE c.increases IS NOT NULL
        """
    )

    # 4. Drop the JSONB payload — the child rows are the source now.
    op.drop_column("character_asi_choices", "increases")


def downgrade() -> None:
    """Downgrade schema."""

    # Rebuild the legacy JSONB payloads from the child rows before
    # dropping them (grandfathered or not — data is data).
    op.add_column(
        "character_asi_choices",
        sa.Column("increases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE character_asi_choices c
        SET increases = rebuilt.payload
        FROM (
            SELECT character_asi_choice_id,
                   jsonb_agg(jsonb_build_object('ability', ability::text, 'amount', amount)) AS payload
            FROM character_asi_choice_increases
            GROUP BY character_asi_choice_id
        ) AS rebuilt
        WHERE c.id = rebuilt.character_asi_choice_id
        """
    )

    op.drop_column("character_asi_choices", "applied_to_base")
    op.drop_index(
        op.f("ix_character_asi_choice_increases_character_asi_choice_id"),
        table_name="character_asi_choice_increases",
    )
    op.drop_table("character_asi_choice_increases")
