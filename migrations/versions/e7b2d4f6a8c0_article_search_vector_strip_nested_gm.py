"""article search_vector: strip GM blocks that contain nested containers

Security fix. ``articles.search_vector`` (what non-GM readers search) is a generated column built from the
body and excerpt with ``:::gm ... :::`` blocks stripped. The flat pattern ``:::gm.*?(:::|$)`` closes a block at
the first ``:::``, so for an article stored BEFORE nested containers were rejected on write
(``:::gm secret :::spoiler more secret ::: tail :::``) everything after the inner ``:::`` stayed in the index and a
non-GM could find the article by its secret words. The application's own read paths (snippets, excerpts,
``gm_stripped_sql``) already strip such a block from ``:::gm`` to the end of the text first (fail closed); this
revision makes the generated column do the same.

Why a column rebuild rather than an UPDATE: a generated column cannot be assigned, and PostgreSQL 15 has no
``ALTER COLUMN ... SET EXPRESSION`` (PG 17+). So the column and its GIN index are dropped and re-added; adding
a STORED generated column recomputes it for EVERY existing row, which is the "recompute search_vector for existing
articles" data migration. The logic is expressible in SQL, so no management command is needed. The regex is the same
one as ``NESTED_GM_BLOCK_SQL_PATTERN`` (``app/features/articles/secrets.py`` / ``app/models/articles/article_model.py``),
frozen here on purpose: a migration must not change when app code does.

Lock impact: ``ALTER TABLE ... ADD COLUMN ... STORED`` rewrites ``articles`` under ACCESS EXCLUSIVE (a small catalog
table). ``search_vector_gm`` (the GM-side index, secrets included) is untouched.

Data check (read-only, safe to run before deploying): the articles this revision changes the search behaviour of::

    SELECT id, slug FROM articles
    WHERE body_markdown ~* ':::gm(?:(?!:::).)*:::[a-z]' OR excerpt ~* ':::gm(?:(?!:::).)*:::[a-z]';

Downgrade restores the flat expression (the leak comes back for such rows) and recomputes the column.

Revision ID: e7b2d4f6a8c0
Revises: d6a2c8e4f0b1
Create Date: 2026-10-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e7b2d4f6a8c0"
down_revision: Union[str, None] = "d6a2c8e4f0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GM_BLOCK = "(?i):::gm.*?(:::|$)"
NESTED_GM_BLOCK = r"(?i):::gm(?:(?!:::).)*:::[a-z].*"


def _flat(column: str) -> str:
    return f"regexp_replace(coalesce({column}, ''), '{GM_BLOCK}', ' ', 'g')"


def _nested_safe(column: str) -> str:
    without_nested = f"regexp_replace(coalesce({column}, ''), '{NESTED_GM_BLOCK}', ' ', 'g')"
    return f"regexp_replace({without_nested}, '{GM_BLOCK}', ' ', 'g')"


def _search_vector_sql(excerpt_sql: str, body_sql: str) -> str:
    """Weighted tsvector: title A > excerpt B > body C, ``russian`` + ``simple`` configs (as in ``article_model``)."""

    return (
        "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
        f"setweight(to_tsvector('russian', {excerpt_sql}), 'B') || "
        f"setweight(to_tsvector('russian', {body_sql}), 'C') || "
        f"setweight(to_tsvector('simple', {body_sql}), 'C')"
    )


def _rebuild_search_vector(excerpt_sql: str, body_sql: str) -> None:
    """Drop and re-add the generated ``search_vector`` (and its GIN index) over the given expressions."""

    op.execute("DROP INDEX IF EXISTS ix_articles_search_vector")
    op.execute("ALTER TABLE articles DROP COLUMN search_vector")
    op.execute(
        "ALTER TABLE articles ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_search_vector_sql(excerpt_sql, body_sql)}) STORED"
    )
    op.execute("CREATE INDEX ix_articles_search_vector ON articles USING gin (search_vector)")


def upgrade() -> None:
    """Upgrade schema."""

    _rebuild_search_vector(_nested_safe("excerpt"), _nested_safe("body_markdown"))


def downgrade() -> None:
    """Downgrade schema."""

    _rebuild_search_vector(_flat("excerpt"), _flat("body_markdown"))
