"""remove feat as a feature source

Feats are de facto their own features — the benefit text lives in the
feat's description, so separate FEAT-source ``features`` rows are no
longer modeled:

  1. delete character_features grants pointing at FEAT-source features;
  2. delete the FEAT-source feature rows themselves;
  3. drop ``features.feat_id`` (column + index + FK).

The 'FEAT' value stays inside the Postgres ENUM type
``feature_source_type`` — Postgres cannot drop enum values. The Python
``FeatureSourceType`` enum simply no longer contains it, so nothing can
write it again.

Revision ID: a9d4f2e8b1c7
Revises: f7c1b8d3a5e2
Create Date: 2026-08-23 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d4f2e8b1c7"
down_revision: Union[str, None] = "f7c1b8d3a5e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove every FEAT-source feature row and the feat_id column."""

    # Grants first (the FK from character_features cascades on feature
    # delete, but an explicit delete keeps the intent readable and avoids
    # relying on DB-level cascade ordering).
    op.execute(
        """
        DELETE FROM character_features
        WHERE feature_id IN (
            SELECT id FROM features WHERE source_type = 'FEAT'
        )
        """
    )
    op.execute("DELETE FROM features WHERE source_type = 'FEAT'")

    op.drop_index(op.f("ix_features_feat_id"), table_name="features")
    op.drop_constraint("fk_features_feat_id_feats", "features", type_="foreignkey")
    op.drop_column("features", "feat_id")


def downgrade() -> None:
    """Restore the feat_id column (data is unrecoverable and not restored)."""

    op.add_column(
        "features",
        sa.Column("feat_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_features_feat_id_feats",
        "features",
        "feats",
        ["feat_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_features_feat_id"), "features", ["feat_id"], unique=False)
