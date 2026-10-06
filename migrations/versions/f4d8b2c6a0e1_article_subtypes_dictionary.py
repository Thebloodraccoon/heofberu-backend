"""article subtypes dictionary

Free-text ``articles.subtype`` becomes a GM-managed dictionary:

- ``article_subtypes`` (``id``, ``article_type``, ``name``), name unique per type ignoring case;
- ``articles.subtype_id`` FK (``ON DELETE SET NULL``) replaces ``articles.subtype``.

Existing values are carried over: one subtype per distinct (``article_type``, trimmed
lower-cased ``subtype``), keeping the first-seen spelling, and every article is linked to it.

Revision ID: f4d8b2c6a0e1
Revises: e2c6a8f4d0b7
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4d8b2c6a0e1"
down_revision: Union[str, None] = "e2c6a8f4d0b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "article_subtypes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_subtypes_article_type"), "article_subtypes", ["article_type"], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX uq_article_subtypes_type_name_lower ON article_subtypes (article_type, lower(name))"
    )

    op.execute(
        """
        INSERT INTO article_subtypes (article_type, name)
        SELECT DISTINCT ON (article_type, lower(btrim(subtype))) article_type, btrim(subtype)
        FROM articles
        WHERE subtype IS NOT NULL AND btrim(subtype) <> ''
        ORDER BY article_type, lower(btrim(subtype)), id
        """
    )

    op.add_column("articles", sa.Column("subtype_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "articles_subtype_id_fkey", "articles", "article_subtypes", ["subtype_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(op.f("ix_articles_subtype_id"), "articles", ["subtype_id"], unique=False)
    op.execute(
        """
        UPDATE articles a SET subtype_id = s.id
        FROM article_subtypes s
        WHERE s.article_type = a.article_type AND lower(s.name) = lower(btrim(a.subtype))
        """
    )

    op.drop_index("ix_articles_subtype", table_name="articles")
    op.drop_column("articles", "subtype")


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column("articles", sa.Column("subtype", sa.String(length=50), nullable=True))
    op.create_index("ix_articles_subtype", "articles", ["subtype"], unique=False)
    op.execute("UPDATE articles a SET subtype = s.name FROM article_subtypes s WHERE s.id = a.subtype_id")

    op.drop_index(op.f("ix_articles_subtype_id"), table_name="articles")
    op.drop_constraint("articles_subtype_id_fkey", "articles", type_="foreignkey")
    op.drop_column("articles", "subtype_id")

    op.drop_index("uq_article_subtypes_type_name_lower", table_name="article_subtypes")
    op.drop_index(op.f("ix_article_subtypes_article_type"), table_name="article_subtypes")
    op.drop_table("article_subtypes")
