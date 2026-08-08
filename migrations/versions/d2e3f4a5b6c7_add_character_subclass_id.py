"""add character subclass id

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-08-08 20:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Free-text subclass label is replaced by a FK to the subclasses table.
    op.drop_column("characters", "subclass")
    op.add_column("characters", sa.Column("subclass_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_characters_subclass_id"), "characters", ["subclass_id"], unique=False)
    op.create_foreign_key(
        "fk_characters_subclass_id_subclasses", "characters", "subclasses", ["subclass_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_characters_subclass_id_subclasses", "characters", type_="foreignkey")
    op.drop_index(op.f("ix_characters_subclass_id"), table_name="characters")
    op.drop_column("characters", "subclass_id")
    op.add_column(
        "characters",
        sa.Column("subclass", sa.String(length=100), nullable=False, server_default=sa.text("''::character varying")),
    )
