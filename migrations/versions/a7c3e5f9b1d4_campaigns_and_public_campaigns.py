"""campaigns: game campaigns, public campaigns (presets) and character public visibility

- ``public_campaigns`` (+ ``public_campaign_tags``, ``public_campaign_articles``): presets any GM writes and
  everyone reads once published; ``slug`` is unique and never changes on rename; trigram GIN indexes on ``title``
  and ``pitch`` serve the catalog's ``ILIKE '%x%'`` search;
- ``campaigns``: one GM's table. ``owner_id`` / ``public_campaign_id`` are ``SET NULL`` (deleting the GM's account or
  the preset keeps the campaign);
- ``campaign_characters``: participation history. ``uq_campaign_characters_one_active`` (partial unique on
  ``character_id`` WHERE ``status = 'ACTIVE'``) keeps a character active in at most one campaign; the character
  access check reads this row;
- ``campaign_sessions`` (number unique per campaign; ``scheduled_at`` + ``ix_campaign_sessions_campaign_scheduled``
  feed the players' schedule), ``campaign_session_attendance`` (who attended: session <-> participation),
  ``campaign_notes``, ``campaign_reviews`` (one per player and campaign), ``session_reviews`` (one per player and
  session);
- ``characters.public_visibility`` (``HIDDEN`` for every existing character: nothing is shown without the owner).

Statuses are VARCHAR(20) holding the enum member NAME (``SAEnum(native_enum=False)``, like ``users.role``), no
CHECK: the sets are product-driven and may grow without a migration.

No data migration: existing GM <-> character links are not stored anywhere, so after this revision a GM reaches a
player's sheet only once the character is added to one of the GM's campaigns.

Revision ID: a7c3e5f9b1d4
Revises: f5a1d7c3e9b2
Create Date: 2026-10-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c3e5f9b1d4"
down_revision: Union[str, None] = "f5a1d7c3e9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    """Upgrade schema (tables in FK order: presets first, reviews last)."""

    op.create_table(
        "public_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("pitch", sa.String(length=500), nullable=False),
        sa.Column("description_markdown", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        *_timestamps(),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_public_campaigns_author_id"), "public_campaigns", ["author_id"], unique=False)
    op.create_index(op.f("ix_public_campaigns_slug"), "public_campaigns", ["slug"], unique=True)
    op.create_index(op.f("ix_public_campaigns_status"), "public_campaigns", ["status"], unique=False)
    for column in ("title", "pitch"):
        op.create_index(
            f"ix_public_campaigns_{column}_trgm",
            "public_campaigns",
            [column],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )

    op.create_table(
        "public_campaign_tags",
        sa.Column("public_campaign_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["public_campaign_id"], ["public_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("public_campaign_id", "tag_id"),
    )
    op.create_index("ix_public_campaign_tags_tag_id", "public_campaign_tags", ["tag_id"], unique=False)

    op.create_table(
        "public_campaign_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_campaign_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["public_campaign_id"], ["public_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_campaign_id", "article_id", name="uq_public_campaign_articles_article"),
    )
    op.create_index(
        op.f("ix_public_campaign_articles_article_id"), "public_campaign_articles", ["article_id"], unique=False
    )

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("public_campaign_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description_markdown", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PLANNING", nullable=False),
        *_timestamps(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["public_campaign_id"], ["public_campaigns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_campaigns_owner_id"), "campaigns", ["owner_id"], unique=False)
    op.create_index(op.f("ix_campaigns_public_campaign_id"), "campaigns", ["public_campaign_id"], unique=False)
    op.create_index(op.f("ix_campaigns_status"), "campaigns", ["status"], unique=False)

    op.create_table(
        "campaign_characters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_characters_campaign_status", "campaign_characters", ["campaign_id", "status"], unique=False
    )
    op.create_index("ix_campaign_characters_character_id", "campaign_characters", ["character_id"], unique=False)
    op.create_index(op.f("ix_campaign_characters_user_id"), "campaign_characters", ["user_id"], unique=False)
    # Autogenerate can't see the predicate: keep it equal to the model's ``postgresql_where``.
    op.create_index(
        "uq_campaign_characters_one_active",
        "campaign_characters",
        ["character_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "campaign_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PLANNED", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chronicle_markdown", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "number", name="uq_campaign_sessions_number"),
    )
    op.create_index(
        "ix_campaign_sessions_campaign_scheduled", "campaign_sessions", ["campaign_id", "scheduled_at"], unique=False
    )

    op.create_table(
        "campaign_session_attendance",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("participation_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["participation_id"], ["campaign_characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["campaign_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "participation_id"),
    )
    op.create_index(
        "ix_campaign_session_attendance_participation_id",
        "campaign_session_attendance",
        ["participation_id"],
        unique=False,
    )

    op.create_table(
        "campaign_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_notes_campaign_id", "campaign_notes", ["campaign_id"], unique=False)

    op.create_table(
        "campaign_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "author_id", name="uq_campaign_reviews_author"),
    )
    op.create_index(op.f("ix_campaign_reviews_author_id"), "campaign_reviews", ["author_id"], unique=False)

    op.create_table(
        "session_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visible_to_table", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["campaign_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "author_id", name="uq_session_reviews_author"),
    )
    op.create_index(op.f("ix_session_reviews_author_id"), "session_reviews", ["author_id"], unique=False)

    op.add_column(
        "characters",
        sa.Column("public_visibility", sa.String(length=20), server_default="HIDDEN", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema (reverse FK order; indexes go with their tables). Campaign data is lost."""

    op.drop_column("characters", "public_visibility")
    for table in (
        "session_reviews",
        "campaign_reviews",
        "campaign_notes",
        "campaign_session_attendance",
        "campaign_sessions",
        "campaign_characters",
        "campaigns",
        "public_campaign_articles",
        "public_campaign_tags",
        "public_campaigns",
    ):
        op.drop_table(table)
