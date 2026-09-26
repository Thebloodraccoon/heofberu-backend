"""unify tags into a shared dictionary

Retires the subrace-only ``subrace_tags`` reference table
(``c8f4e2a6b9d3``) in favor of one shared ``tags`` dictionary reusable
across unrelated catalogs. Each catalog keeps its own typed m2m link table
(real FK on the "tagged" side, matching ``app/models/tag_model.py`` and the
per-catalog association modules):

- ``race_tags``       (new)
- ``subrace_tags``    (replaces the old reference table of the same name —
                        the old reference table and ``subrace_tag_links`` are
                        dropped, and this becomes the races/subraces link
                        table instead, matching ``race_tags``/
                        ``background_tags`` naming)
- ``background_tags`` (new)

Existing subrace tag rows/links are preserved: each distinct tag name is
copied once into ``tags``, and every ``subrace_tag_links`` row is repointed
at the new ``tags.id`` before the old tables are dropped.

Revision ID: a031c08480da
Revises: b7e4d1f2a9c6
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a031c08480da"
down_revision: Union[str, None] = "b7e4d1f2a9c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()

    # --- Shared tags dictionary ---
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_tags_name"), "tags", ["name"], unique=True)

    # --- Migrate existing subrace tag names into the shared dictionary ---
    bind.execute(sa.text("INSERT INTO tags (name) SELECT name FROM subrace_tags"))

    # --- Stage the repointed subrace<->tag links before dropping the old tables ---
    bind.execute(
        sa.text(
            """
            CREATE TABLE _subrace_tags_migration_staging AS
            SELECT stl.subrace_id AS subrace_id, t.id AS tag_id
            FROM subrace_tag_links stl
            JOIN subrace_tags st ON st.id = stl.subrace_tag_id
            JOIN tags t ON t.name = st.name
            """
        )
    )

    op.drop_table("subrace_tag_links")
    op.drop_index(op.f("ix_subrace_tags_name"), table_name="subrace_tags")
    op.drop_table("subrace_tags")

    # --- New link tables (races/subraces/backgrounds <-> tags) ---
    op.create_table(
        "race_tags",
        sa.Column("race_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["race_id"], ["races.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("race_id", "tag_id"),
    )
    op.create_index(op.f("ix_race_tags_tag_id"), "race_tags", ["tag_id"], unique=False)

    op.create_table(
        "subrace_tags",
        sa.Column("subrace_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["subrace_id"], ["subraces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("subrace_id", "tag_id"),
    )
    op.create_index(op.f("ix_subrace_tags_tag_id"), "subrace_tags", ["tag_id"], unique=False)

    op.create_table(
        "background_tags",
        sa.Column("background_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["background_id"], ["backgrounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("background_id", "tag_id"),
    )
    op.create_index(op.f("ix_background_tags_tag_id"), "background_tags", ["tag_id"], unique=False)

    bind.execute(sa.text("INSERT INTO subrace_tags (subrace_id, tag_id) SELECT subrace_id, tag_id FROM _subrace_tags_migration_staging"))
    op.execute("DROP TABLE _subrace_tags_migration_staging")


def downgrade() -> None:
    """
    Downgrade schema.

    Only ``subrace_tags`` links have a pre-migration home to go back to (the old
    reference table restored below). ``race_tags``/``background_tags`` didn't
    exist before this migration, so there's nowhere to put their rows on
    downgrade — dropping those tables while they hold any data would silently
    and permanently delete it. Refuse instead: an operator who's sure that data
    is disposable can truncate ``race_tags``/``background_tags`` and re-run.
    """

    bind = op.get_bind()

    for table in ("race_tags", "background_tags"):
        (count,) = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).fetchone()
        if count:
            raise RuntimeError(
                f"Refusing to downgrade: '{table}' holds {count} row(s) with no pre-migration table to "
                "restore them into. Truncate it first if that data may be discarded."
            )

    # --- Stage the current subrace<->tag links before dropping the new table ---
    bind.execute(
        sa.text(
            """
            CREATE TABLE _subrace_tags_migration_staging AS
            SELECT subrace_id, tag_id FROM subrace_tags
            """
        )
    )

    op.drop_index(op.f("ix_background_tags_tag_id"), table_name="background_tags")
    op.drop_table("background_tags")

    op.drop_index(op.f("ix_subrace_tags_tag_id"), table_name="subrace_tags")
    op.drop_table("subrace_tags")

    op.drop_index(op.f("ix_race_tags_tag_id"), table_name="race_tags")
    op.drop_table("race_tags")

    # --- Restore the old subrace-only reference table + link table (best-effort) ---
    op.create_table(
        "subrace_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_subrace_tags_name"), "subrace_tags", ["name"], unique=True)

    bind.execute(
        sa.text(
            """
            INSERT INTO subrace_tags (name)
            SELECT DISTINCT t.name
            FROM _subrace_tags_migration_staging s
            JOIN tags t ON t.id = s.tag_id
            """
        )
    )

    op.create_table(
        "subrace_tag_links",
        sa.Column("subrace_id", sa.Integer(), nullable=False),
        sa.Column("subrace_tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["subrace_id"], ["subraces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subrace_tag_id"], ["subrace_tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("subrace_id", "subrace_tag_id"),
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO subrace_tag_links (subrace_id, subrace_tag_id)
            SELECT s.subrace_id, st.id
            FROM _subrace_tags_migration_staging s
            JOIN tags t ON t.id = s.tag_id
            JOIN subrace_tags st ON st.name = t.name
            """
        )
    )

    op.execute("DROP TABLE _subrace_tags_migration_staging")

    op.drop_index(op.f("ix_tags_name"), table_name="tags")
    op.drop_table("tags")
