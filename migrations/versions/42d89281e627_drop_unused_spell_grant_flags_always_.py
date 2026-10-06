"""
drop unused spell grant flags always_prepared and counts_against_known_limit

Both flags were fully wired end-to-end (feature engine effect -> materializer
-> character_granted_spells -> known-spell-limit eligibility check) but never
actually varied anything meaningful in practice: ``always_prepared``
described a "prepared slot" concept the spellcasting model never otherwise
implements (knowing a spell IS having it ready — see
``CharacterSpellService``), and ``counts_against_known_limit`` was exercised
by exactly one test fixture, never by real catalog content. Dropping both;
granted spells no longer compete for the known-spell budget.

Revision ID: 42d89281e627
Revises: 771ee792d001
Create Date: 2026-09-12 12:44:53.751196

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "42d89281e627"
down_revision: str | None = "771ee792d001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the two meaningless flag columns from both spell-grant tables."""
    op.drop_column("character_granted_spells", "counts_against_known_limit")
    op.drop_column("character_granted_spells", "always_prepared")
    op.drop_column("feature_spell_grant_effects", "counts_against_known_limit")
    op.drop_column("feature_spell_grant_effects", "always_prepared")


def downgrade() -> None:
    """Restore the columns with their original defaults."""
    op.add_column(
        "feature_spell_grant_effects",
        sa.Column("always_prepared", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "feature_spell_grant_effects",
        sa.Column("counts_against_known_limit", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "character_granted_spells",
        sa.Column("always_prepared", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "character_granted_spells",
        sa.Column("counts_against_known_limit", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
