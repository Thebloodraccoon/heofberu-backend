"""indexes: association/FK indexes, listing indexes, trigram search; drop indexes covered by a unique index

Pure index changes, no data is read or written, so the revision cannot fail on existing data.

Added
  * ``spell_classes/spell_subclasses/spell_races/spell_subraces``: index on the SECOND key column. Each PK leads
    with ``spell_id``, so "spells of class X" and the ON DELETE CASCADE from classes/subclasses/races/subraces
    scanned the whole association table.
  * ``articles.reviewed_by_id``: FK with ON DELETE SET NULL (deleting a user scanned ``articles``).
  * ``ix_articles_public_title`` / ``ix_articles_public_published``: partial indexes for the non-GM listing
    (``status = 'PUBLISHED' AND visibility = 'PUBLIC'``) sorted by ``(title, id)`` or by
    ``(COALESCE(published_at, created_at) DESC, id DESC)``.
  * ``characters (owner_id, name, id)`` for ``GET /characters`` (owner filter + ``ORDER BY name, id``) and a
    ``pg_trgm`` GIN index on ``characters.name`` for ``ILIKE '%x%'`` (the extension is created by revision 0001).

Dropped (each is the leading column of an existing unique index, so it only slows writes)
  * ``ix_article_relations_from_article_id``   <- ``uq_article_relation (from_article_id, to_article_id, relation_type)``
  * ``ix_subclasses_class_id``                 <- ``uq_subclass_class_id_name (class_id, name)``
  * ``ix_subraces_race_id``                    <- ``uq_subrace_race_id_name (race_id, name)``
  * ``ix_character_features_character_id``     <- ``uq_character_features_character_feature (character_id, feature_id)``
  * ``ix_character_feature_choices_character_feature_id`` <- ``uq_character_feature_choice_option (character_feature_id, ...)``
  * ``ix_character_asi_choices_character_id``  <- ``uq_character_asi_choice_level (character_id, class_level)``
  * ``ix_characters_owner_id``                 <- the new ``ix_characters_owner_id_name``

Deliberately NOT dropped: ``ix_races_name`` / ``ix_classes_name`` (with ``unique=True, index=True`` SQLAlchemy emits
ONE unique index of that name: dropping it would drop the uniqueness), ``ix_subraces_name`` / ``ix_subclasses_name``
(not covered by any other index) and the single-column article ``status`` / ``visibility`` / ``article_type`` indexes
(need EXPLAIN on production data first).

Lock impact: plain ``CREATE INDEX`` (SHARE lock, blocks writes to that table while it builds). The project's migrations
run one transaction per revision with no autocommit blocks, and ``CREATE INDEX CONCURRENTLY`` cannot run inside a
transaction; the tables here are small, so the lock lasts well under a second. If a table ever grows large, create
the new indexes by hand with ``CREATE INDEX CONCURRENTLY`` first and swap them in a later revision.

Revision ID: f8c3e5a7b9d1
Revises: e7b2d4f6a8c0
Create Date: 2026-10-01 10:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8c3e5a7b9d1"
down_revision: Union[str, None] = "e7b2d4f6a8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PUBLIC_ROW = sa.text("status = 'PUBLISHED' AND visibility = 'PUBLIC'")

#: (index, table, columns) for the spell association second-column indexes.
_ASSOCIATION_INDEXES = (
    ("ix_spell_classes_class_id", "spell_classes", ["class_id"]),
    ("ix_spell_subclasses_subclass_id", "spell_subclasses", ["subclass_id"]),
    ("ix_spell_races_race_id", "spell_races", ["race_id"]),
    ("ix_spell_subraces_subrace_id", "spell_subraces", ["subrace_id"]),
)

#: (index, table, column) covered by a unique index that leads with the same column.
_REDUNDANT_INDEXES = (
    ("ix_article_relations_from_article_id", "article_relations", "from_article_id"),
    ("ix_subclasses_class_id", "subclasses", "class_id"),
    ("ix_subraces_race_id", "subraces", "race_id"),
    ("ix_character_features_character_id", "character_features", "character_id"),
    ("ix_character_feature_choices_character_feature_id", "character_feature_choices", "character_feature_id"),
    ("ix_character_asi_choices_character_id", "character_asi_choices", "character_id"),
    ("ix_characters_owner_id", "characters", "owner_id"),
)


def upgrade() -> None:
    """Upgrade schema."""

    for name, table, columns in _ASSOCIATION_INDEXES:
        op.create_index(name, table, columns)

    op.create_index("ix_articles_reviewed_by_id", "articles", ["reviewed_by_id"])
    op.create_index("ix_articles_public_title", "articles", ["title", "id"], postgresql_where=_PUBLIC_ROW)
    op.create_index(
        "ix_articles_public_published",
        "articles",
        [sa.text("COALESCE(published_at, created_at) DESC"), sa.text("id DESC")],
        postgresql_where=_PUBLIC_ROW,
    )

    op.create_index("ix_characters_owner_id_name", "characters", ["owner_id", "name", "id"])
    op.create_index(
        "ix_characters_name_trgm",
        "characters",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    for name, table, _column in _REDUNDANT_INDEXES:
        op.drop_index(name, table_name=table)


def downgrade() -> None:
    """Downgrade schema."""

    for name, table, column in reversed(_REDUNDANT_INDEXES):
        op.create_index(name, table, [column])

    op.drop_index("ix_characters_name_trgm", table_name="characters", postgresql_using="gin")
    op.drop_index("ix_characters_owner_id_name", table_name="characters")

    op.drop_index("ix_articles_public_published", table_name="articles")
    op.drop_index("ix_articles_public_title", table_name="articles")
    op.drop_index("ix_articles_reviewed_by_id", table_name="articles")

    for name, table, _columns in reversed(_ASSOCIATION_INDEXES):
        op.drop_index(name, table_name=table)
