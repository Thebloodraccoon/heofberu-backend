"""
drop feature_choice_groups.label

The group's label duplicated what a client can already infer from its
``choice_type`` and options' effects — a fully abstract choice-group render
(see app.features.features.effects.rendering / PendingChoiceGroup) needs no
free-text name for the decision. The choice OPTION's own label was already
dropped for the same reason (see e6dde395e1a0); this drops the group's.

Revision ID: 76676c656c28
Revises: 5c2b6d2ff132
Create Date: 2026-09-15 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "76676c656c28"
down_revision: str | None = "5c2b6d2ff132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the redundant label column from feature_choice_groups."""
    op.drop_column("feature_choice_groups", "label")


def downgrade() -> None:
    """Restore the column, empty for every existing row."""
    op.add_column(
        "feature_choice_groups",
        sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
    )
