"""article: GM blocks stripped from the public excerpt index

``articles.search_vector`` is rebuilt so the excerpt (weight B) is indexed with
``:::gm ... :::`` blocks stripped too, not just the body. Matches ``SEARCH_VECTOR_SQL``
in ``app/models/articles/article_model.py``.

Revision ID: d8b4f0a2c6e9
Revises: c7a3e9d1b5f2
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d8b4f0a2c6e9"
down_revision: Union[str, None] = "c7a3e9d1b5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GM_BLOCK = "(?i):::gm.*?(:::|$)"
PUBLIC_BODY_SQL = f"regexp_replace(coalesce(body_markdown, ''), '{GM_BLOCK}', ' ', 'g')"
PUBLIC_EXCERPT_SQL = f"regexp_replace(coalesce(excerpt, ''), '{GM_BLOCK}', ' ', 'g')"
FULL_EXCERPT_SQL = "coalesce(excerpt, '')"


def _search_vector_sql(excerpt_sql: str, body_sql: str) -> str:
    """Weighted tsvector: title A > ``excerpt_sql`` B > ``body_sql`` C, ``russian`` + ``simple`` configs."""

    return (
        "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
        f"setweight(to_tsvector('russian', {excerpt_sql}), 'B') || "
        f"setweight(to_tsvector('russian', {body_sql}), 'C') || "
        f"setweight(to_tsvector('simple', {body_sql}), 'C')"
    )


def _replace_search_vector(excerpt_sql: str) -> None:
    """Drop and re-add the generated ``search_vector`` column (and its index) over ``excerpt_sql``."""

    op.execute("DROP INDEX IF EXISTS ix_articles_search_vector")
    op.execute("ALTER TABLE articles DROP COLUMN search_vector")
    op.execute(
        "ALTER TABLE articles ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_search_vector_sql(excerpt_sql, PUBLIC_BODY_SQL)}) STORED"
    )
    op.execute("CREATE INDEX ix_articles_search_vector ON articles USING gin (search_vector)")


def upgrade() -> None:
    """Upgrade schema."""

    _replace_search_vector(PUBLIC_EXCERPT_SQL)


def downgrade() -> None:
    """Downgrade schema."""

    _replace_search_vector(FULL_EXCERPT_SQL)
