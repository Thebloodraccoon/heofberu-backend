"""article GM-only blocks, subtype and per-relation visibility

- ``articles.search_vector`` is rebuilt to index the body with ``:::gm ... :::`` blocks
  stripped, so non-GM search can't match (or snippet) a secret; the new
  ``articles.search_vector_gm`` indexes the full body for GM search. Both GIN-indexed.
  Matches ``SEARCH_VECTOR_SQL``/``SEARCH_VECTOR_GM_SQL`` in ``app/models/articles/article_model.py``.
- ``articles.subtype`` — nullable free-text refinement of ``article_type`` (location → «таверна»).
- ``article_relations.visibility`` (``PUBLIC``/``GM_ONLY``, default ``PUBLIC``) — hides a
  relation from non-GMs even when both articles are public.

Revision ID: d2b8f6c41a97
Revises: 705548ecfb46
Create Date: 2026-09-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2b8f6c41a97"
down_revision: Union[str, None] = "705548ecfb46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

article_visibility_enum = postgresql.ENUM("PUBLIC", "GM_ONLY", name="article_visibility", create_type=False)

FULL_BODY_SQL = "coalesce(body_markdown, '')"
PUBLIC_BODY_SQL = "regexp_replace(coalesce(body_markdown, ''), ':::gm.*?(:::|$)', ' ', 'g')"


def _search_vector_sql(body_sql: str) -> str:
    """Weighted tsvector: title A > excerpt B > ``body_sql`` C, ``russian`` + ``simple`` configs."""

    return (
        "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('russian', coalesce(excerpt, '')), 'B') || "
        f"setweight(to_tsvector('russian', {body_sql}), 'C') || "
        f"setweight(to_tsvector('simple', {body_sql}), 'C')"
    )


def _replace_search_vector(body_sql: str) -> None:
    """Drop and re-add the generated ``search_vector`` column (and its index) over ``body_sql``."""

    op.execute("DROP INDEX IF EXISTS ix_articles_search_vector")
    op.execute("ALTER TABLE articles DROP COLUMN search_vector")
    op.execute(
        "ALTER TABLE articles ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_search_vector_sql(body_sql)}) STORED"
    )
    op.execute("CREATE INDEX ix_articles_search_vector ON articles USING gin (search_vector)")


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column("articles", sa.Column("subtype", sa.String(length=50), nullable=True))
    op.create_index(op.f("ix_articles_subtype"), "articles", ["subtype"], unique=False)

    op.add_column(
        "article_relations",
        sa.Column("visibility", article_visibility_enum, nullable=False, server_default="PUBLIC"),
    )

    _replace_search_vector(PUBLIC_BODY_SQL)
    op.execute(
        "ALTER TABLE articles ADD COLUMN search_vector_gm tsvector "
        f"GENERATED ALWAYS AS ({_search_vector_sql(FULL_BODY_SQL)}) STORED"
    )
    op.execute("CREATE INDEX ix_articles_search_vector_gm ON articles USING gin (search_vector_gm)")


def downgrade() -> None:
    """Downgrade schema."""

    op.execute("DROP INDEX IF EXISTS ix_articles_search_vector_gm")
    op.execute("ALTER TABLE articles DROP COLUMN search_vector_gm")
    _replace_search_vector(FULL_BODY_SQL)

    op.drop_column("article_relations", "visibility")

    op.drop_index(op.f("ix_articles_subtype"), table_name="articles")
    op.drop_column("articles", "subtype")
