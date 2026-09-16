"""unify proficiencies, background suggestions/gold, drop skill key, missing indexes

Consolidated migration covering several independent model changes made in
the same session:

1. Proficiency unification: the four typed "materialized state" tables
   (``character_skill_proficiencies``, ``character_saving_throw_proficiencies``,
   ``character_armor_proficiencies``, ``character_weapon_proficiencies``) and
   the audit log (``character_proficiency_audit_log``) are DROPPED and
   replaced by one table, ``character_proficiencies`` — both current state
   and provenance (who/what granted it) live there now; see
   ``app/models/character/character_proficiency_model.py`` for the full
   resolution algorithm and indexing rationale. Dev data only, not migrated:
   existing rows in the five dropped tables are gone, not carried over.

2. ``character_items`` drops ``is_equipped``/``is_attuned``/``notes``;
   ``character_features`` drops ``notes`` (dead free-text fields, no
   replacement — the GM notes-on-a-feature-grant feature was removed
   entirely, taking the ``PATCH /gm-panel/features`` notes-only endpoint
   with it).

3. ``backgrounds`` drops its four free-text suggestion blobs
   (``personality_traits_suggestions``/``ideals_suggestions``/
   ``bonds_suggestions``/``flaws_suggestions``), replaced by one row per
   suggestion in the new ``background_suggestions`` table (tagged by
   ``suggestion_type``, unordered — picked from the set or rolled at
   random). ``backgrounds`` gains ``starting_gold``.

4. ``skills.key`` (a stable English code, e.g. "PERCEPTION") is dropped —
   with no localization system actually consuming it separately from
   ``name``, it was a redundant second unique field; ``name`` becomes the
   sole unique+indexed identifier.

5. Missing indexes added: ``character_asi_choices.ability_score_increase_id``;
   ``skill_id`` on ``race_skills``/``class_available_skills``/
   ``background_skills`` (their composite PK is ``(x_id, skill_id)``, which
   can't serve a lone ``WHERE skill_id = ...`` — used by the skill-deletion
   in-use guard).

Revision ID: f3a5c7e9b1d4
Revises: a1b2c3d4e5f6
Create Date: 2026-09-11 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f3a5c7e9b1d4"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ability_score_enum = postgresql.ENUM(
    "STR", "DEX", "CON", "INT", "WIS", "CHA", name="ability_score", create_type=False
)
armor_proficiency_enum = postgresql.ENUM(
    "LIGHT", "MEDIUM", "HEAVY", "SHIELD", name="armor_proficiency", create_type=False
)
weapon_proficiency_enum = postgresql.ENUM("SIMPLE", "MARTIAL", name="weapon_proficiency", create_type=False)
proficiency_type_enum = postgresql.ENUM(
    "SKILL", "SAVING_THROW", "ARMOR", "WEAPON", name="proficiency_type", create_type=False
)
proficiency_source_type_enum = postgresql.ENUM(
    "CLASS_CHOICE",
    "RACE",
    "BACKGROUND",
    "FEATURE",
    "FEATURE_CHOICE",
    "GM",
    name="proficiency_source_type",
    create_type=False,
)
proficiency_action_enum = postgresql.ENUM("GRANT", "REVOKE", name="proficiency_action", create_type=False)
feature_grant_source_enum = postgresql.ENUM("AUTO", "GM", "ASI", name="feature_grant_source", create_type=False)
feature_source_type_enum = postgresql.ENUM(
    "CLASS", "SUBCLASS", "RACE", "SUBRACE", "BACKGROUND", "FEAT", "OTHER", name="feature_source_type", create_type=False
)
background_suggestion_type_enum = postgresql.ENUM(
    "PERSONALITY_TRAIT", "IDEAL", "BOND", "FLAW", name="background_suggestion_type", create_type=False
)

_DISCRIMINATOR_SHAPE = (
    "(proficiency_type = 'SKILL' AND skill_id IS NOT NULL AND ability IS NULL "
    "AND armor_type IS NULL AND weapon_category IS NULL AND item_id IS NULL)"
    " OR "
    "(proficiency_type = 'SAVING_THROW' AND ability IS NOT NULL AND skill_id IS NULL "
    "AND armor_type IS NULL AND weapon_category IS NULL AND item_id IS NULL)"
    " OR "
    "(proficiency_type = 'ARMOR' AND armor_type IS NOT NULL AND skill_id IS NULL "
    "AND ability IS NULL AND weapon_category IS NULL AND item_id IS NULL)"
    " OR "
    "(proficiency_type = 'WEAPON' AND skill_id IS NULL AND ability IS NULL AND armor_type IS NULL "
    "AND ((weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)))"
)


def upgrade() -> None:
    """Upgrade schema."""

    # ==================================================================
    # 1. Proficiency unification
    # ==================================================================

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE proficiency_source_type AS ENUM
                ('CLASS_CHOICE', 'RACE', 'BACKGROUND', 'FEATURE', 'FEATURE_CHOICE', 'GM');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE proficiency_action AS ENUM ('GRANT', 'REVOKE');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.create_table(
        "character_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("proficiency_type", proficiency_type_enum, nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=True),
        sa.Column("ability", ability_score_enum, nullable=True),
        sa.Column("armor_type", armor_proficiency_enum, nullable=True),
        sa.Column("weapon_category", weapon_proficiency_enum, nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("source_type", proficiency_source_type_enum, nullable=False),
        sa.Column("action", proficiency_action_enum, nullable=False, server_default="GRANT"),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.Column("grant_source", feature_grant_source_enum, nullable=True),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("feature_source_type", feature_source_type_enum, nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("is_expertise", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_DISCRIMINATOR_SHAPE, name="ck_character_proficiency_discriminator_shape"),
    )

    # Every real query filters (character_id, proficiency_type, one
    # discriminator column) together — this composite covers the first two
    # and narrows to a handful of rows, making a plain character_id index
    # redundant.
    op.create_index(
        "ix_character_proficiency_character_type", "character_proficiencies", ["character_id", "proficiency_type"]
    )
    for col in ("skill_id", "item_id", "source_character_feature_id", "feature_id", "actor_user_id"):
        op.create_index(op.f(f"ix_character_proficiencies_{col}"), "character_proficiencies", [col])

    # At most one GM row per (character, proficiency) — upserted, not appended.
    op.create_index(
        "uq_character_proficiency_gm_skill",
        "character_proficiencies",
        ["character_id", "skill_id"],
        unique=True,
        postgresql_where=sa.text("source_type = 'GM' AND proficiency_type = 'SKILL'"),
    )
    op.create_index(
        "uq_character_proficiency_gm_save",
        "character_proficiencies",
        ["character_id", "ability"],
        unique=True,
        postgresql_where=sa.text("source_type = 'GM' AND proficiency_type = 'SAVING_THROW'"),
    )
    op.create_index(
        "uq_character_proficiency_gm_armor",
        "character_proficiencies",
        ["character_id", "armor_type"],
        unique=True,
        postgresql_where=sa.text("source_type = 'GM' AND proficiency_type = 'ARMOR'"),
    )
    op.create_index(
        "uq_character_proficiency_gm_weapon_category",
        "character_proficiencies",
        ["character_id", "weapon_category"],
        unique=True,
        postgresql_where=sa.text(
            "source_type = 'GM' AND proficiency_type = 'WEAPON' AND weapon_category IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_character_proficiency_gm_weapon_item",
        "character_proficiencies",
        ["character_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("source_type = 'GM' AND proficiency_type = 'WEAPON' AND item_id IS NOT NULL"),
    )

    # At most one row per (grant, proficiency) — re-materializing an
    # unchanged grant must never duplicate its own row.
    op.create_index(
        "uq_character_proficiency_grant_skill",
        "character_proficiencies",
        ["source_character_feature_id", "skill_id"],
        unique=True,
        postgresql_where=sa.text("source_character_feature_id IS NOT NULL AND proficiency_type = 'SKILL'"),
    )
    op.create_index(
        "uq_character_proficiency_grant_save",
        "character_proficiencies",
        ["source_character_feature_id", "ability"],
        unique=True,
        postgresql_where=sa.text("source_character_feature_id IS NOT NULL AND proficiency_type = 'SAVING_THROW'"),
    )
    op.create_index(
        "uq_character_proficiency_grant_armor",
        "character_proficiencies",
        ["source_character_feature_id", "armor_type"],
        unique=True,
        postgresql_where=sa.text("source_character_feature_id IS NOT NULL AND proficiency_type = 'ARMOR'"),
    )
    op.create_index(
        "uq_character_proficiency_grant_weapon_category",
        "character_proficiencies",
        ["source_character_feature_id", "weapon_category"],
        unique=True,
        postgresql_where=sa.text(
            "source_character_feature_id IS NOT NULL AND proficiency_type = 'WEAPON' "
            "AND weapon_category IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_character_proficiency_grant_weapon_item",
        "character_proficiencies",
        ["source_character_feature_id", "item_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_character_feature_id IS NOT NULL AND proficiency_type = 'WEAPON' AND item_id IS NOT NULL"
        ),
    )

    # --- Drop the four typed tables + the audit log ---
    op.drop_table("character_saving_throw_proficiencies")
    op.drop_table("character_armor_proficiencies")
    op.drop_table("character_weapon_proficiencies")

    op.drop_index(
        op.f("ix_character_skill_proficiencies_source_character_feature_id"),
        table_name="character_skill_proficiencies",
    )
    op.drop_table("character_skill_proficiencies")

    op.drop_index(
        op.f("ix_character_proficiency_audit_log_actor_user_id"), table_name="character_proficiency_audit_log"
    )
    op.drop_index(
        op.f("ix_character_proficiency_audit_log_character_id"), table_name="character_proficiency_audit_log"
    )
    op.drop_table("character_proficiency_audit_log")
    op.execute("DROP TYPE IF EXISTS proficiency_audit_action")

    # ==================================================================
    # 2. Dead free-text fields
    # ==================================================================

    op.drop_column("character_items", "is_equipped")
    op.drop_column("character_items", "is_attuned")
    op.drop_column("character_items", "notes")
    op.drop_column("character_features", "notes")

    # ==================================================================
    # 3. Background suggestions + starting gold
    # ==================================================================

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE background_suggestion_type AS ENUM
                ('PERSONALITY_TRAIT', 'IDEAL', 'BOND', 'FLAW');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.create_table(
        "background_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("background_id", sa.Integer(), nullable=False),
        sa.Column("suggestion_type", background_suggestion_type_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["background_id"], ["backgrounds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_background_suggestions_background_id"), "background_suggestions", ["background_id"]
    )

    op.drop_column("backgrounds", "personality_traits_suggestions")
    op.drop_column("backgrounds", "ideals_suggestions")
    op.drop_column("backgrounds", "bonds_suggestions")
    op.drop_column("backgrounds", "flaws_suggestions")
    op.add_column("backgrounds", sa.Column("starting_gold", sa.Integer(), nullable=False, server_default="0"))

    # ==================================================================
    # 4. Drop skills.key, name becomes the unique identifier
    # ==================================================================

    op.drop_index(op.f("ix_skills_key"), table_name="skills")
    op.drop_column("skills", "key")
    op.create_index(op.f("ix_skills_name"), "skills", ["name"], unique=True)

    # ==================================================================
    # 5. Missing indexes
    # ==================================================================

    op.create_index(
        op.f("ix_character_asi_choices_ability_score_increase_id"),
        "character_asi_choices",
        ["ability_score_increase_id"],
    )
    op.create_index("ix_race_skills_skill_id", "race_skills", ["skill_id"])
    op.create_index("ix_class_available_skills_skill_id", "class_available_skills", ["skill_id"])
    op.create_index("ix_background_skills_skill_id", "background_skills", ["skill_id"])


def downgrade() -> None:
    """Downgrade schema."""

    # --- 5. Missing indexes ---
    op.drop_index("ix_background_skills_skill_id", table_name="background_skills")
    op.drop_index("ix_class_available_skills_skill_id", table_name="class_available_skills")
    op.drop_index("ix_race_skills_skill_id", table_name="race_skills")
    op.drop_index(
        op.f("ix_character_asi_choices_ability_score_increase_id"), table_name="character_asi_choices"
    )

    # --- 4. Restore skills.key ---
    # Best-effort: the original key values are gone (dropped, not archived),
    # so this backfills from `name` instead of a constant default — a
    # constant would collide on the unique index the moment there's more
    # than one skill row. `name` is unique at this point, so deriving from
    # it is too.
    op.drop_index(op.f("ix_skills_name"), table_name="skills")
    op.add_column("skills", sa.Column("key", sa.String(length=50), nullable=True))
    op.execute("UPDATE skills SET key = UPPER(name)")
    op.alter_column("skills", "key", nullable=False)
    op.create_index(op.f("ix_skills_key"), "skills", ["key"], unique=True)

    # --- 3. Restore background suggestion columns, drop the table + starting_gold ---
    op.drop_column("backgrounds", "starting_gold")
    op.add_column(
        "backgrounds", sa.Column("flaws_suggestions", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "backgrounds", sa.Column("bonds_suggestions", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "backgrounds", sa.Column("ideals_suggestions", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "backgrounds", sa.Column("personality_traits_suggestions", sa.Text(), nullable=False, server_default="")
    )

    op.drop_index(op.f("ix_background_suggestions_background_id"), table_name="background_suggestions")
    op.drop_table("background_suggestions")
    op.execute("DROP TYPE IF EXISTS background_suggestion_type")

    # --- 2. Restore dead free-text fields ---
    op.add_column("character_features", sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    op.add_column("character_items", sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "character_items", sa.Column("is_attuned", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "character_items", sa.Column("is_equipped", sa.Boolean(), nullable=False, server_default=sa.false())
    )

    # --- 1. Restore the four typed tables + audit log, drop the unified table ---
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE proficiency_audit_action AS ENUM
                ('ADD', 'REMOVE', 'EXPERTISE_GRANTED', 'EXPERTISE_REVOKED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.create_table(
        "character_proficiency_audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("proficiency_type", proficiency_type_enum, nullable=False),
        sa.Column(
            "action",
            postgresql.ENUM(
                "ADD",
                "REMOVE",
                "EXPERTISE_GRANTED",
                "EXPERTISE_REVOKED",
                name="proficiency_audit_action",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("skill_id", sa.Integer(), nullable=True),
        sa.Column("ability", ability_score_enum, nullable=True),
        sa.Column("armor_type", armor_proficiency_enum, nullable=True),
        sa.Column("weapon_category", weapon_proficiency_enum, nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_character_proficiency_audit_log_character_id"), "character_proficiency_audit_log", ["character_id"]
    )
    op.create_index(
        op.f("ix_character_proficiency_audit_log_actor_user_id"),
        "character_proficiency_audit_log",
        ["actor_user_id"],
    )

    op.create_table(
        "character_skill_proficiencies",
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("is_expertise", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_character_feature_id"],
            ["character_features.id"],
            ondelete="CASCADE",
            name="fk_character_skill_proficiencies_source_grant",
        ),
        sa.PrimaryKeyConstraint("character_id", "skill_id"),
    )
    op.create_index(
        op.f("ix_character_skill_proficiencies_source_character_feature_id"),
        "character_skill_proficiencies",
        ["source_character_feature_id"],
    )

    op.create_table(
        "character_saving_throw_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "ability", name="uq_character_saving_throw_ability"),
    )
    for col in ("character_id", "source_character_feature_id"):
        op.create_index(
            op.f(f"ix_character_saving_throw_proficiencies_{col}"), "character_saving_throw_proficiencies", [col]
        )

    op.create_table(
        "character_armor_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("armor_type", armor_proficiency_enum, nullable=False),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "armor_type", name="uq_character_armor_proficiency_type"),
    )
    for col in ("character_id", "source_character_feature_id"):
        op.create_index(op.f(f"ix_character_armor_proficiencies_{col}"), "character_armor_proficiencies", [col])

    op.create_table(
        "character_weapon_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("weapon_category", weapon_proficiency_enum, nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "item_id", name="uq_character_weapon_proficiency_item"),
        sa.CheckConstraint(
            "(weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)",
            name="ck_character_weapon_proficiency_one_target",
        ),
    )
    for col in ("character_id", "item_id", "source_character_feature_id"):
        op.create_index(op.f(f"ix_character_weapon_proficiencies_{col}"), "character_weapon_proficiencies", [col])

    # Drop the unified table (indexes/constraints go with it).
    op.drop_table("character_proficiencies")
    op.execute("DROP TYPE IF EXISTS proficiency_action")
    op.execute("DROP TYPE IF EXISTS proficiency_source_type")
