"""lowercase tag and article subtype names

The API now stores both names lowercased; existing rows are converted here. Lowercased in Python, not with SQL
``lower()``, which leaves Cyrillic as is under the ``C`` collation. No duplicates can appear: both tables are already
unique on ``lower(name)``. Not reversible (the original casing is lost), so the downgrade is a no-op.

Revision ID: e2c6a4f8d0b3
Revises: d7b3e9a1c5f2
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2c6a4f8d0b3"
down_revision: Union[str, None] = "d7b3e9a1c5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    for table in ("tags", "article_subtypes"):
        rows = bind.execute(sa.text(f"SELECT id, name FROM {table}")).all()
        for row_id, name in rows:
            if name != name.lower():
                bind.execute(
                    sa.text(f"UPDATE {table} SET name = :name WHERE id = :id"), {"name": name.lower(), "id": row_id}
                )


def downgrade() -> None:
    """Downgrade schema (no-op: the original casing isn't kept)."""
