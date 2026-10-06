"""Add class armor proficiencies, source-owned starting equipment, and drop character personality fields

Adds the two new reference sub-resources:
  - ``class_armor_proficiencies``: armor categories (LIGHT/MEDIUM/HEAVY/
    SHIELD) a class grants proficiency in;
  - ``source_items``: starting-equipment entries owned by a class or
    background (polymorphic, mirroring ``features``).

Also drops the character personality fields (``personality_traits``,
``ideals``, ``bonds``, ``flaws``) that were removed from the character
model/schemas — the free-text ``traits``/``backstory``/``notes`` sections
remain.

Revision ID: e7f8a9b0c1d2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    def _create_enum_safely(enum_name, values):
        values_sql = ", ".join(f"'{v}'" for v in values)
        op.execute(
            f"""
            DO $$
            BEGIN
                CREATE TYPE {enum_name} AS ENUM ({values_sql});
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
            """
        )

    _create_enum_safely("armor_proficiency", ["LIGHT", "MEDIUM", "HEAVY", "SHIELD"])

    op.create_table(
        "class_armor_proficiencies",
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column(
            "armor_type",
            postgresql.ENUM("LIGHT", "MEDIUM", "HEAVY", "SHIELD", name="armor_proficiency", create_type=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("class_id", "armor_type"),
    )

    op.create_table(
        "source_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "CLASS",
                "SUBCLASS",
                "RACE",
                "BACKGROUND",
                "FEAT",
                "OTHER",
                name="feature_source_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("background_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="check_source_item_quantity_nonnegative"),
        sa.ForeignKeyConstraint(["background_id"], ["backgrounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_source_items_class_id"), "source_items", ["class_id"], unique=False)
    op.create_index(op.f("ix_source_items_item_id"), "source_items", ["item_id"], unique=False)
    op.create_index(op.f("ix_source_items_background_id"), "source_items", ["background_id"], unique=False)
    op.create_index(op.f("ix_source_items_source_type"), "source_items", ["source_type"], unique=False)

    op.drop_column("characters", "personality_traits")
    op.drop_column("characters", "ideals")
    op.drop_column("characters", "bonds")
    op.drop_column("characters", "flaws")


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column("characters", sa.Column("personality_traits", sa.Text(), nullable=False, server_default=""))
    op.add_column("characters", sa.Column("ideals", sa.Text(), nullable=False, server_default=""))
    op.add_column("characters", sa.Column("bonds", sa.Text(), nullable=False, server_default=""))
    op.add_column("characters", sa.Column("flaws", sa.Text(), nullable=False, server_default=""))

    op.drop_index(op.f("ix_source_items_source_type"), table_name="source_items")
    op.drop_index(op.f("ix_source_items_background_id"), table_name="source_items")
    op.drop_index(op.f("ix_source_items_item_id"), table_name="source_items")
    op.drop_index(op.f("ix_source_items_class_id"), table_name="source_items")
    op.drop_table("source_items")
    op.drop_table("class_armor_proficiencies")
    op.execute("DROP TYPE IF EXISTS armor_proficiency")
