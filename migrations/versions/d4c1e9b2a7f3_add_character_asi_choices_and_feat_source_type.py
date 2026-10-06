"""add character_asi_choices and feat grant source_type

Revision ID: d4c1e9b2a7f3
Revises: 2bea8b331f7a
Create Date: 2026-08-06 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4c1e9b2a7f3"
down_revision: Union[str, None] = "2bea8b331f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

asi_choice_enum = postgresql.ENUM(
    "ASI",
    "FEAT",
    name="asi_choice",
    create_type=False,
)
character_feat_source_enum = postgresql.ENUM(
    "GM",
    "ORIGIN",
    "ASI",
    name="character_feat_source",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    postgresql.ENUM("ASI", "FEAT", name="asi_choice").create(op.get_bind(), checkfirst=True)
    postgresql.ENUM("GM", "ORIGIN", "ASI", name="character_feat_source").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "character_asi_choices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("class_level", sa.Integer(), nullable=False),
        sa.Column("choice_type", asi_choice_enum, nullable=False),
        sa.Column("feat_id", sa.Integer(), nullable=True),
        sa.Column("ability_score_increase_id", sa.Integer(), nullable=True),
        sa.Column("increases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ability_score_increase_id"], ["feat_ability_score_increases.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["feat_id"], ["feats.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "class_level", name="uq_character_asi_choice_level"),
    )
    op.create_index(
        op.f("ix_character_asi_choices_character_id"), "character_asi_choices", ["character_id"], unique=False
    )
    op.create_index(op.f("ix_character_asi_choices_feat_id"), "character_asi_choices", ["feat_id"], unique=False)

    op.add_column(
        "character_feats",
        sa.Column(
            "source_type",
            character_feat_source_enum,
            nullable=False,
            server_default="GM",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("character_feats", "source_type")
    op.drop_index(op.f("ix_character_asi_choices_feat_id"), table_name="character_asi_choices")
    op.drop_index(op.f("ix_character_asi_choices_character_id"), table_name="character_asi_choices")
    op.drop_table("character_asi_choices")

    postgresql.ENUM("ASI", "FEAT", name="asi_choice").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM("GM", "ORIGIN", "ASI", name="character_feat_source").drop(op.get_bind(), checkfirst=True)
