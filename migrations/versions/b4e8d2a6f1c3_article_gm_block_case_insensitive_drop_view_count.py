"""article GM-block marker case-insensitive, drop view_count

- ``articles.search_vector`` is rebuilt with a case-insensitive GM-block pattern
  (``(?i):::gm.*?(:::|$)``), so ``:::GM`` / ``:::Gm`` blocks are stripped from the
  non-GM index too. Matches ``SEARCH_VECTOR_SQL`` in ``app/models/articles/article_model.py``.
- ``articles.view_count`` is dropped — it was never incremented.

Revision ID: b4e8d2a6f1c3
Revises: e5c1a7d93f02
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4e8d2a6f1c3"
down_revision: Union[str, None] = "e5c1a7d93f02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CASE_INSENSITIVE_BODY_SQL = "regexp_replace(coalesce(body_markdown, ''), '(?i):::gm.*?(:::|$)', ' ', 'g')"
CASE_SENSITIVE_BODY_SQL = "regexp_replace(coalesce(body_markdown, ''), ':::gm.*?(:::|$)', ' ', 'g')"


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

    _replace_search_vector(CASE_INSENSITIVE_BODY_SQL)
    op.drop_column("articles", "view_count")


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column("articles", sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"))
    _replace_search_vector(CASE_SENSITIVE_BODY_SQL)
