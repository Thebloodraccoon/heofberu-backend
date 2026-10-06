"""article visibility, full-text search and case-insensitive tag names

- ``articles.visibility`` (``PUBLIC`` / ``GM_ONLY``) — spoiler/prep-note articles
  hidden from non-GMs, independent of the publication ``status``.
- ``articles.search_vector`` — generated tsvector (title A > excerpt B > body C,
  ``russian`` + ``simple`` configs) with a GIN index, plus a ``pg_trgm`` GIN index
  on ``title`` for typo-tolerant title search (``pg_trgm`` comes from
  ``0001_install_extensions``). Matches ``SEARCH_VECTOR_SQL`` in
  ``app/models/articles/article_model.py``.
- ``tags``: unique index on ``lower(name)`` so "Nordavingar" and "nordavingar"
  can't coexist. Case-only duplicates (if any survived from the pre-unification
  per-catalog tags tables) are merged into the lowest-id row of each group first,
  repointing every ``race_tags``/``subrace_tags``/``background_tags``/``article_tags``
  link before the losing rows are dropped, so the index creation itself never fails.

Revision ID: 705548ecfb46
Revises: 4ffb883f9582
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "705548ecfb46"
down_revision: Union[str, None] = "4ffb883f9582"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

article_visibility_enum = postgresql.ENUM("PUBLIC", "GM_ONLY", name="article_visibility", create_type=False)

SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('russian', coalesce(excerpt, '')), 'B') || "
    "setweight(to_tsvector('russian', coalesce(body_markdown, '')), 'C') || "
    "setweight(to_tsvector('simple', coalesce(body_markdown, '')), 'C')"
)


#: Every tag-link table with a ``(entity_id, tag_id)`` composite PK, keyed by its entity column.
TAG_LINK_TABLES = {
    "race_tags": "race_id",
    "subrace_tags": "subrace_id",
    "background_tags": "background_id",
    "article_tags": "article_id",
}


def _merge_case_only_duplicate_tags() -> None:
    """
    Merge tags that differ only by case into the lowest-id row of each group.

    For each group, every link-table row pointing at a "losing" duplicate is
    repointed at the keeper (dropped instead, if the keeper is already linked
    to the same entity, to avoid a composite-PK conflict), then the losing
    tag rows themselves are deleted. Runs before ``uq_tags_name_lower`` is
    created so pre-existing case-only duplicates can't abort the migration.
    """

    op.execute(
        "CREATE TEMP TABLE _tag_dupe_merge AS "
        "SELECT t.id AS loser_id, keep.keeper_id FROM tags t "
        "JOIN (SELECT lower(name) AS lname, min(id) AS keeper_id FROM tags "
        "      GROUP BY lower(name) HAVING count(*) > 1) keep "
        "ON lower(t.name) = keep.lname "
        "WHERE t.id != keep.keeper_id"
    )

    for table, entity_column in TAG_LINK_TABLES.items():
        op.execute(
            f"UPDATE {table} link SET tag_id = m.keeper_id "
            f"FROM _tag_dupe_merge m "
            f"WHERE link.tag_id = m.loser_id "
            f"AND NOT EXISTS (SELECT 1 FROM {table} existing "
            f"WHERE existing.{entity_column} = link.{entity_column} AND existing.tag_id = m.keeper_id)"
        )
        op.execute(f"DELETE FROM {table} link USING _tag_dupe_merge m WHERE link.tag_id = m.loser_id")

    op.execute("DELETE FROM tags t USING _tag_dupe_merge m WHERE t.id = m.loser_id")
    op.execute("DROP TABLE _tag_dupe_merge")


def upgrade() -> None:
    """Upgrade schema."""

    article_visibility_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "articles",
        sa.Column("visibility", article_visibility_enum, nullable=False, server_default="PUBLIC"),
    )
    op.create_index(op.f("ix_articles_visibility"), "articles", ["visibility"], unique=False)

    op.execute(
        f"ALTER TABLE articles ADD COLUMN search_vector tsvector GENERATED ALWAYS AS ({SEARCH_VECTOR_SQL}) STORED"
    )
    op.execute("CREATE INDEX ix_articles_search_vector ON articles USING gin (search_vector)")
    op.execute("CREATE INDEX ix_articles_title_trgm ON articles USING gin (title gin_trgm_ops)")

    _merge_case_only_duplicate_tags()

    op.execute("CREATE UNIQUE INDEX uq_tags_name_lower ON tags (lower(name))")


def downgrade() -> None:
    """Downgrade schema."""

    op.execute("DROP INDEX IF EXISTS uq_tags_name_lower")

    op.execute("DROP INDEX IF EXISTS ix_articles_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_articles_search_vector")
    op.execute("ALTER TABLE articles DROP COLUMN search_vector")

    op.drop_index(op.f("ix_articles_visibility"), table_name="articles")
    op.drop_column("articles", "visibility")
    article_visibility_enum.drop(op.get_bind(), checkfirst=True)
