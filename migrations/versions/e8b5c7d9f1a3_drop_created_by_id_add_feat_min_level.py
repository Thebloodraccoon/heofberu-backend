"""drop created_by_id everywhere, add feats.min_level

Revision ID: e8b5c7d9f1a3
Revises: c3e7a1f9d2b4
Create Date: 2026-08-25 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8b5c7d9f1a3"
down_revision: Union[str, None] = "c3e7a1f9d2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables carrying the now-unused ``created_by_id`` attribution column.
TABLES = (
    "races",
    "subraces",
    "classes",
    "subclasses",
    "backgrounds",
    "items",
    "spells",
    "features",
    "feats",
)


def upgrade() -> None:
    """Drop ``created_by_id`` from all reference tables; add ``feats.min_level``.

    ``created_by_id`` was never read anywhere (only written on create),
    so the column, its index and its FK to ``users.id`` are removed.
    ``feats.min_level`` is a bare nullable int — validation of the value
    happens in the Pydantic schemas, not in the database.
    """
    for table in TABLES:
        op.drop_index(op.f(f"ix_{table}_created_by_id"), table_name=table)
        op.drop_constraint(f"{table}_created_by_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "created_by_id")

    op.add_column("feats", sa.Column("min_level", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Restore ``created_by_id`` (all NULL) and drop ``feats.min_level``."""
    op.drop_column("feats", "min_level")

    for table in TABLES:
        op.add_column(
            table,
            sa.Column("created_by_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            f"{table}_created_by_id_fkey",
            source_table=table,
            referent_table="users",
            local_cols=["created_by_id"],
            remote_cols=["id"],
            ondelete="SET NULL",
        )
        op.create_index(op.f(f"ix_{table}_created_by_id"), table, ["created_by_id"])
