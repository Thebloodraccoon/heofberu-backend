"""article proposals; reviewer and content hash on revisions

- ``article_revisions.reviewer_id`` (``SET NULL``): who approved the version; existing ones were all direct edits,
  so they are self-reviewed (``reviewer_id = editor_id``);
- ``article_revisions.content_hash``: git-like SHA-256 chain (``revisions.hashing.revision_hash``), backfilled
  per article in version order;
- ``article_proposals``: proposed changes to someone else's article (pending / accepted / rejected).

Revision ID: d7b3e9a1c5f2
Revises: c4a8e2f6b1d9
Create Date: 2026-10-02 00:00:00.000000

"""

import hashlib
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d7b3e9a1c5f2"
down_revision: Union[str, None] = "c4a8e2f6b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTENT_FIELDS = ("title", "excerpt", "body_markdown", "article_type", "subtype_id", "visibility")


def _revision_hash(parent_hash, version, content):
    """Frozen copy of ``app.features.articles.revisions.hashing.revision_hash`` (keep in sync for the backfill)."""

    payload = {**content, "parent": parent_hash, "version": version}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column("article_revisions", sa.Column("reviewer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "article_revisions_reviewer_id_fkey",
        "article_revisions",
        "users",
        ["reviewer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_article_revisions_reviewer_id"), "article_revisions", ["reviewer_id"], unique=False)
    op.execute("UPDATE article_revisions SET reviewer_id = editor_id")

    op.add_column("article_revisions", sa.Column("content_hash", sa.String(length=64), nullable=True))
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT id, article_id, version, title, excerpt, body_markdown, article_type, subtype_id, "
                "lower(visibility::text) AS visibility FROM article_revisions ORDER BY article_id, version"
            )
        )
        .mappings()
        .all()
    )
    hashes: dict[tuple[int, int], str] = {}
    for row in rows:
        content = {field: row[field] for field in CONTENT_FIELDS}
        digest = _revision_hash(hashes.get((row["article_id"], row["version"] - 1)), row["version"], content)
        hashes[(row["article_id"], row["version"])] = digest
        bind.execute(
            sa.text("UPDATE article_revisions SET content_hash = :h WHERE id = :id"), {"h": digest, "id": row["id"]}
        )
    op.alter_column("article_revisions", "content_hash", nullable=False)

    proposal_status = postgresql.ENUM("PENDING", "ACCEPTED", "REJECTED", name="article_proposal_status")
    proposal_status.create(bind, checkfirst=True)

    op.create_table(
        "article_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("proposer_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("excerpt", sa.String(length=500), nullable=True),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("article_type", sa.String(length=50), nullable=False),
        sa.Column("subtype_id", sa.Integer(), nullable=True),
        sa.Column(
            "visibility",
            postgresql.ENUM("PUBLIC", "GM_ONLY", name="article_visibility", create_type=False),
            nullable=False,
        ),
        sa.Column("change_note", sa.String(length=300), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "ACCEPTED", "REJECTED", name="article_proposal_status", create_type=False),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_proposals_article_id"), "article_proposals", ["article_id"], unique=False)
    op.create_index(op.f("ix_article_proposals_proposer_id"), "article_proposals", ["proposer_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_article_proposals_proposer_id"), table_name="article_proposals")
    op.drop_index(op.f("ix_article_proposals_article_id"), table_name="article_proposals")
    op.drop_table("article_proposals")
    postgresql.ENUM(name="article_proposal_status").drop(op.get_bind(), checkfirst=True)

    op.drop_column("article_revisions", "content_hash")
    op.drop_index(op.f("ix_article_revisions_reviewer_id"), table_name="article_revisions")
    op.drop_constraint("article_revisions_reviewer_id_fkey", "article_revisions", type_="foreignkey")
    op.drop_column("article_revisions", "reviewer_id")
