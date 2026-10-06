"""article proposals: withdrawn status and review note

- ``article_proposal_status`` gets ``WITHDRAWN`` (the proposer took a pending proposal back);
- ``article_proposals.review_note``: the reviewer's optional reason for a rejection.

Revision ID: f5a1d7c3e9b2
Revises: e2c6a4f8d0b3
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5a1d7c3e9b2"
down_revision: Union[str, None] = "e2c6a4f8d0b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("ALTER TYPE article_proposal_status ADD VALUE IF NOT EXISTS 'WITHDRAWN'")
    op.add_column("article_proposals", sa.Column("review_note", sa.String(length=300), nullable=True))


def downgrade() -> None:
    """Downgrade schema (Postgres can't drop an enum value: withdrawn proposals become rejected, the value stays)."""

    op.drop_column("article_proposals", "review_note")
    op.execute("UPDATE article_proposals SET status = 'REJECTED' WHERE status = 'WITHDRAWN'")
