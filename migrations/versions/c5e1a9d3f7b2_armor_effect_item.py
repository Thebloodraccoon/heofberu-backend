"""armor proficiency effect: a category or one concrete armor item

``feature_armor_proficiency_effects`` gets ``item_id`` (FK ``items``, RESTRICT) and ``armor_type``
becomes nullable; exactly one of the two is set (``ck_feature_armor_proficiency_one_target``), like
the weapon proficiency effect. The downgrade deletes item-targeted rows (the old schema can't hold
them).

Revision ID: c5e1a9d3f7b2
Revises: b2d8f4a6c1e3
Create Date: 2026-10-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5e1a9d3f7b2"
down_revision: Union[str, None] = "b2d8f4a6c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feature_armor_proficiency_effects", sa.Column("item_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "feature_armor_proficiency_effects_item_id_fkey",
        "feature_armor_proficiency_effects",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_feature_armor_proficiency_effects_item_id", "feature_armor_proficiency_effects", ["item_id"]
    )
    op.alter_column("feature_armor_proficiency_effects", "armor_type", nullable=True)
    op.create_check_constraint(
        "ck_feature_armor_proficiency_one_target",
        "feature_armor_proficiency_effects",
        "(armor_type IS NOT NULL AND item_id IS NULL) OR (armor_type IS NULL AND item_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_armor_proficiency_effects WHERE item_id IS NOT NULL")
    op.drop_constraint(
        "ck_feature_armor_proficiency_one_target", "feature_armor_proficiency_effects", type_="check"
    )
    op.alter_column("feature_armor_proficiency_effects", "armor_type", nullable=False)
    op.drop_index("ix_feature_armor_proficiency_effects_item_id", table_name="feature_armor_proficiency_effects")
    op.drop_constraint(
        "feature_armor_proficiency_effects_item_id_fkey", "feature_armor_proficiency_effects", type_="foreignkey"
    )
    op.drop_column("feature_armor_proficiency_effects", "item_id")
