"""db audit: indexes and constraints

- ``character_features``: ``UNIQUE(character_id, feature_id)`` — repositories read the pair with
  ``scalar_one_or_none()``, so a duplicate grant would 500. Aborts with the offending pairs if
  duplicates already exist (resolve them by hand, then re-run).
- ``articles.path``: GiST instead of B-tree (ltree ``<@``/``@>`` can't use B-tree).
- ``character_spells.spell_id``: index (the composite PK leads with ``character_id``; the spell
  delete cascade and ``exists_referencing`` filter by ``spell_id``).
- Redundant uniqueness dropped: ``articles_slug_key`` (``ix_articles_slug`` is unique),
  ``tags_name_key`` + ``ix_tags_name`` (``uq_tags_name_lower`` covers them), ``ix_users_id`` (PK).

Revision ID: a5e9c3f7b1d2
Revises: f4d8b2c6a0e1
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a5e9c3f7b1d2"
down_revision: Union[str, None] = "f4d8b2c6a0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT character_id, feature_id, count(*) FROM character_features "
                "GROUP BY character_id, feature_id HAVING count(*) > 1"
            )
        )
        .fetchall()
    )
    if duplicates:
        raise RuntimeError(f"Duplicate character_features (character_id, feature_id, count): {duplicates}")
    op.create_unique_constraint(
        "uq_character_features_character_feature", "character_features", ["character_id", "feature_id"]
    )

    op.drop_index("ix_articles_path", table_name="articles")
    op.execute("CREATE INDEX ix_articles_path ON articles USING gist (path)")

    op.create_index(op.f("ix_character_spells_spell_id"), "character_spells", ["spell_id"], unique=False)

    op.drop_constraint("articles_slug_key", "articles", type_="unique")
    op.drop_constraint("tags_name_key", "tags", type_="unique")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_index("ix_users_id", table_name="users")


def downgrade() -> None:
    """Downgrade schema."""

    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_tags_name", "tags", ["name"], unique=True)
    op.create_unique_constraint("tags_name_key", "tags", ["name"])
    op.create_unique_constraint("articles_slug_key", "articles", ["slug"])

    op.drop_index(op.f("ix_character_spells_spell_id"), table_name="character_spells")

    op.drop_index("ix_articles_path", table_name="articles")
    op.create_index("ix_articles_path", "articles", ["path"], unique=False)

    op.drop_constraint("uq_character_features_character_feature", "character_features", type_="unique")
