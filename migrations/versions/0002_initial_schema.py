"""Initial schema: users, races, characters, attacks, spells

Revision ID: 0002_initial_schema
Revises: 0001_install_extensions
Create Date: 2025-07-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_initial_schema"
down_revision: Union[str, None] = "0001_install_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema for users, races, characters, attacks and spells."""

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="player"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('found_father', 'keeper', 'player')", name="check_user_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # --- races ---
    op.create_table(
        "races",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=False, server_default="Средний"),
        sa.Column("speed", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("ability_bonuses", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("granted_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("traits", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_homebrew", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_races_name"), "races", ["name"], unique=True)
    op.create_index(
        "idx_race_name_trgm",
        "races",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    # --- characters ---
    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("character_class", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("subclass", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("race_id", sa.Integer(), nullable=True),
        sa.Column("current_hp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_hp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temp_hp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_dice", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("speed", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("armor_class", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("shield", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initiative_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passive_perception_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_jack_of_all_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strength", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("dexterity", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("constitution", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("intelligence", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("wisdom", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("charisma", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("skill_proficiencies", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("saving_throw_proficiencies", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("proficiencies", sa.Text(), nullable=False, server_default=""),
        sa.Column("traits", sa.Text(), nullable=False, server_default=""),
        sa.Column("feats", sa.Text(), nullable=False, server_default=""),
        sa.Column("inventory", sa.Text(), nullable=False, server_default=""),
        sa.Column("backstory", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("money_gold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("money_silver", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("money_copper", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spell_ability", sa.String(length=10), nullable=True),
        sa.Column("spell_dc_misc_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spell_attack_misc_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spell_slots", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("level >= 1 AND level <= 20", name="check_character_level_range"),
        sa.CheckConstraint("current_hp >= 0", name="check_current_hp_nonnegative"),
        sa.CheckConstraint("max_hp >= 0", name="check_max_hp_nonnegative"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["race_id"], ["races.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_characters_name"), "characters", ["name"], unique=False)
    op.create_index(op.f("ix_characters_owner_id"), "characters", ["owner_id"], unique=False)
    op.create_index(op.f("ix_characters_race_id"), "characters", ["race_id"], unique=False)
    op.create_index(
        "idx_character_name_trgm",
        "characters",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    # --- spells ---
    op.create_table(
        "spells",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("school", sa.String(length=50), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("cast_time", sa.String(length=50), nullable=False),
        sa.Column("range_type", sa.String(length=30), nullable=False),
        sa.Column("range_value", sa.Integer(), nullable=True),
        sa.Column("components", sa.String(length=100), nullable=False),
        sa.Column("material", sa.Text(), nullable=True),
        sa.Column("is_ritual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duration", sa.String(length=50), nullable=False),
        sa.Column("is_concentration", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attack_type", sa.String(length=20), nullable=False, server_default="NONE"),
        sa.Column("save_stat", sa.String(length=10), nullable=True),
        sa.Column("damage_type", sa.String(length=30), nullable=True),
        sa.Column("damage_dice", sa.String(length=30), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("higher_levels", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_spells_name"), "spells", ["name"], unique=True)
    op.create_index(op.f("ix_spells_level"), "spells", ["level"], unique=False)
    op.create_index("idx_spell_level", "spells", ["level"], unique=False)

    # --- attacks ---
    op.create_table(
        "attacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("attack_type", sa.String(length=30), nullable=False),
        sa.Column("ability", sa.String(length=10), nullable=False),
        sa.Column("is_proficient", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bonus_attack", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonus_damage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("damage_dice", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("damage_type", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("range", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attacks_character_id"), "attacks", ["character_id"], unique=False)

    # --- character_spells (many-to-many) ---
    op.create_table(
        "character_spells",
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("spell_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spell_id"], ["spells.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("character_id", "spell_id"),
    )
    op.create_index("idx_character_spells_character_id", "character_spells", ["character_id"], unique=False)
    op.create_index("idx_character_spells_spell_id", "character_spells", ["spell_id"], unique=False)


def downgrade() -> None:
    """Drop all tables created in this migration, in reverse dependency order."""

    op.drop_index("idx_character_spells_spell_id", table_name="character_spells")
    op.drop_index("idx_character_spells_character_id", table_name="character_spells")
    op.drop_table("character_spells")

    op.drop_index(op.f("ix_attacks_character_id"), table_name="attacks")
    op.drop_table("attacks")

    op.drop_index("idx_spell_level", table_name="spells")
    op.drop_index(op.f("ix_spells_level"), table_name="spells")
    op.drop_index(op.f("ix_spells_name"), table_name="spells")
    op.drop_table("spells")

    op.drop_index(
        "idx_character_name_trgm",
        table_name="characters",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_characters_race_id"), table_name="characters")
    op.drop_index(op.f("ix_characters_owner_id"), table_name="characters")
    op.drop_index(op.f("ix_characters_name"), table_name="characters")
    op.drop_table("characters")

    op.drop_index(
        "idx_race_name_trgm",
        table_name="races",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_races_name"), table_name="races")
    op.drop_table("races")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
