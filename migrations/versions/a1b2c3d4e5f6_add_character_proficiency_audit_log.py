"""add character proficiency audit log

Adds ``character_proficiency_audit_log``: an append-only record of GM
changes (add/remove/expertise toggle) to a character's skill/saving-throw/
armor/weapon proficiency rows. The materialized proficiency tables carry no
history themselves, so a GM removing a proficiency or expertise was
otherwise silent — this table is purely for "who changed what and when"
visibility and is never read back into gameplay logic.

Revision ID: a1b2c3d4e5f6
Revises: d4e6f8a2c1b3
Create Date: 2026-09-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d4e6f8a2c1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the two new enum types and the audit-log table."""

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE proficiency_type AS ENUM ('SKILL', 'SAVING_THROW', 'ARMOR', 'WEAPON');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
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
        sa.Column(
            "proficiency_type",
            postgresql.ENUM(
                "SKILL", "SAVING_THROW", "ARMOR", "WEAPON", name="proficiency_type", create_type=False
            ),
            nullable=False,
        ),
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
        sa.Column(
            "ability",
            postgresql.ENUM(
                "STR", "DEX", "CON", "INT", "WIS", "CHA", name="ability_score", create_type=False
            ),
            nullable=True,
        ),
        sa.Column(
            "armor_type",
            postgresql.ENUM("LIGHT", "MEDIUM", "HEAVY", "SHIELD", name="armor_proficiency", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "weapon_category",
            postgresql.ENUM("SIMPLE", "MARTIAL", name="weapon_proficiency", create_type=False),
            nullable=True,
        ),
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
        op.f("ix_character_proficiency_audit_log_character_id"),
        "character_proficiency_audit_log",
        ["character_id"],
    )
    op.create_index(
        op.f("ix_character_proficiency_audit_log_actor_user_id"),
        "character_proficiency_audit_log",
        ["actor_user_id"],
    )


def downgrade() -> None:
    """Drop the table and the two enum types."""

    op.drop_index(
        op.f("ix_character_proficiency_audit_log_actor_user_id"), table_name="character_proficiency_audit_log"
    )
    op.drop_index(
        op.f("ix_character_proficiency_audit_log_character_id"), table_name="character_proficiency_audit_log"
    )
    op.drop_table("character_proficiency_audit_log")
    op.execute("DROP TYPE IF EXISTS proficiency_audit_action")
    op.execute("DROP TYPE IF EXISTS proficiency_type")
