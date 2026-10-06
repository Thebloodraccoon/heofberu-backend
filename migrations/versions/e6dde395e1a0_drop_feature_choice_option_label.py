"""
drop feature_choice_options.label

An option's label duplicated its effect bundle in free text (e.g. "STR" on
an option whose ability_effects already say STR) with nothing enforcing the
two stay in sync. Choice options are now rendered straight from their
effects (see app.features.features.effects.rendering), so the label column
is dropped; the choice GROUP's own label is untouched — it still names the
overall decision (e.g. "Choose an ability").

Revision ID: e6dde395e1a0
Revises: 42d89281e627
Create Date: 2026-09-12 13:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e6dde395e1a0"
down_revision: str | None = "42d89281e627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the redundant label column from feature_choice_options."""
    op.drop_column("feature_choice_options", "label")


def downgrade() -> None:
    """Restore the column, empty for every existing row."""
    op.add_column(
        "feature_choice_options",
        sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
    )
