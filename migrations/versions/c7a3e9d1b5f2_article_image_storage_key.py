"""article image storage_key (unguessable Storage folder)

``article_images.storage_key`` — a random uuid folder in the Storage object key
(``articles/{article_id}/{storage_key}/{id}.{ext}``). The bucket is public, so with the
old ``articles/{article_id}/{id}.{ext}`` key an image embedded in a ``:::gm`` block or a
draft could be fetched by guessing the sequential ids.

Existing rows get a random key; their old objects (at the id-only path) become orphans —
acceptable, article images only exist on dev databases so far.

Revision ID: c7a3e9d1b5f2
Revises: b4e8d2a6f1c3
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7a3e9d1b5f2"
down_revision: Union[str, None] = "b4e8d2a6f1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column("article_images", sa.Column("storage_key", sa.String(length=36), nullable=True))
    op.execute("UPDATE article_images SET storage_key = gen_random_uuid()::text")
    op.alter_column("article_images", "storage_key", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("article_images", "storage_key")
