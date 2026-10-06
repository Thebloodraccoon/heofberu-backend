"""
Feature/feat grant effects are computed on read: drop their materialized rows and columns.

What a grant gives a character (skills, saves, armor/weapons, spells) is now
derived on every read from the feature's effect tree plus the player's
stored picks (``character_feature_choices``), so the rows the old
materializer wrote are dropped along with the columns only it used:

- ``character_proficiencies``: rows with ``source_character_feature_id`` set
  (``FEATURE``/``FEATURE_CHOICE``), then the columns
  ``source_character_feature_id``/``grant_source``/``feature_id``/
  ``feature_source_type`` (their indexes, FKs and the
  ``uq_character_proficiency_grant_*`` partial unique indexes go with them).
- ``character_granted_spells``: feature-granted rows, then
  ``source_character_feature_id`` — the table keeps only the GM's direct
  grants, now unique per (character, spell) (``uq_character_granted_spell``;
  duplicate GM rows are collapsed first) since the GM panel addresses them
  by ``spell_id``.

Guard: a pick of an open ("any skill"/"any spell") option was only ever
resolved inside the materialized row, so dropping it would lose the
player's concrete choice. The API refuses such picks, but if legacy data
has one the upgrade aborts instead of silently dropping it.

Downgrade restores the columns and indexes but not the rows — re-run the
previous release's feature sync to rebuild them.

Revision ID: d6a2c8e4f0b1
Revises: b6f0d4a8c2e3
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d6a2c8e4f0b1"
down_revision = "b6f0d4a8c2e3"
branch_labels = None
depends_on = None

_OPEN_PICKS_SQL = """
SELECT count(*)
FROM character_feature_choices c
WHERE EXISTS (
    SELECT 1 FROM feature_skill_proficiency_effects e
    WHERE e.choice_option_id = c.choice_option_id AND e.skill_id IS NULL
) OR EXISTS (
    SELECT 1 FROM feature_spell_grant_effects e
    WHERE e.choice_option_id = c.choice_option_id AND e.spell_id IS NULL
)
"""

_PROFICIENCY_GRANT_COLUMNS = ("source_character_feature_id", "grant_source", "feature_id", "feature_source_type")


def upgrade() -> None:
    open_picks = op.get_bind().execute(sa.text(_OPEN_PICKS_SQL)).scalar()
    if open_picks:
        raise RuntimeError(
            f"{open_picks} stored pick(s) point at an open 'any skill/spell' option; their concrete resolution "
            "lives only in the materialized rows this migration drops. Re-answer or delete those picks first."
        )

    op.execute("DELETE FROM character_proficiencies WHERE source_character_feature_id IS NOT NULL")
    op.execute("DELETE FROM character_granted_spells WHERE source_character_feature_id IS NOT NULL")

    for column in _PROFICIENCY_GRANT_COLUMNS:
        op.drop_column("character_proficiencies", column)
    op.drop_column("character_granted_spells", "source_character_feature_id")

    op.execute(
        "DELETE FROM character_granted_spells a USING character_granted_spells b "
        "WHERE a.character_id = b.character_id AND a.spell_id = b.spell_id AND a.id > b.id"
    )
    op.create_unique_constraint("uq_character_granted_spell", "character_granted_spells", ["character_id", "spell_id"])


def downgrade() -> None:
    op.drop_constraint("uq_character_granted_spell", "character_granted_spells", type_="unique")

    feature_grant_source_enum = postgresql.ENUM(name="feature_grant_source", create_type=False)
    feature_source_type_enum = postgresql.ENUM(name="feature_source_type", create_type=False)

    op.add_column("character_granted_spells", sa.Column("source_character_feature_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        None,
        "character_granted_spells",
        "character_features",
        ["source_character_feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_character_granted_spells_source_character_feature_id"),
        "character_granted_spells",
        ["source_character_feature_id"],
    )

    op.add_column("character_proficiencies", sa.Column("source_character_feature_id", sa.Integer(), nullable=True))
    op.add_column("character_proficiencies", sa.Column("grant_source", feature_grant_source_enum, nullable=True))
    op.add_column("character_proficiencies", sa.Column("feature_id", sa.Integer(), nullable=True))
    op.add_column("character_proficiencies", sa.Column("feature_source_type", feature_source_type_enum, nullable=True))
    op.create_foreign_key(
        None,
        "character_proficiencies",
        "character_features",
        ["source_character_feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(None, "character_proficiencies", "features", ["feature_id"], ["id"], ondelete="CASCADE")
    for column in ("source_character_feature_id", "feature_id"):
        op.create_index(op.f(f"ix_character_proficiencies_{column}"), "character_proficiencies", [column])

    for name, column, where in (
        ("skill", "skill_id", "proficiency_type = 'SKILL'"),
        ("save", "ability", "proficiency_type = 'SAVING_THROW'"),
        ("armor", "armor_type", "proficiency_type = 'ARMOR'"),
        ("weapon_category", "weapon_category", "proficiency_type = 'WEAPON' AND weapon_category IS NOT NULL"),
        ("weapon_item", "item_id", "proficiency_type = 'WEAPON' AND item_id IS NOT NULL"),
    ):
        op.create_index(
            f"uq_character_proficiency_grant_{name}",
            "character_proficiencies",
            ["source_character_feature_id", column],
            unique=True,
            postgresql_where=sa.text(f"source_character_feature_id IS NOT NULL AND {where}"),
        )
