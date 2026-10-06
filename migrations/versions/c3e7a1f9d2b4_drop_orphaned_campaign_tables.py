"""drop orphaned campaign tables

The ``campaigns`` / ``campaign_characters`` tables were migrated in
``5bde518ea704`` but no feature, router, or service ever shipped — the
models were dead schema in production. They are removed here; the
campaign feature will re-introduce its own (redesigned) schema when it
is actually built.

Revision ID: c3e7a1f9d2b4
Revises: a9d4f2e8b1c7
Create Date: 2026-08-23 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7a1f9d2b4"
down_revision: Union[str, None] = "a9d4f2e8b1c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the never-used campaign tables (membership table first — it references campaigns)."""

    op.drop_table("campaign_characters")
    op.drop_index(op.f("ix_campaigns_gm_id"), table_name="campaigns")
    op.drop_table("campaigns")


def downgrade() -> None:
    """Recreate the campaign tables (data is unrecoverable)."""

    import sqlalchemy as sa

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gm_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["gm_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_campaigns_gm_id"), "campaigns", ["gm_id"], unique=False)
    op.create_table(
        "campaign_characters",
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("campaign_id", "character_id"),
    )
