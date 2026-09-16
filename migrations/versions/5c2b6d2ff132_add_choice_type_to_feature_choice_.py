"""
add choice_type to feature_choice_groups

Pins each choice group to exactly one effect kind (SKILL, SPELL,
ABILITY_SCORE, SAVING_THROW, ARMOR, WEAPON) — enforced on write by
``ChoiceGroupPayload``'s validator, so an option inside a group can only
ever populate the one effect-list field its group's type allows. Backfills
existing groups by inspecting which effect table their options' rows
actually live in; a group with no options (or none matching any known
type) falls back to SKILL.

Revision ID: 5c2b6d2ff132
Revises: e6dde395e1a0
Create Date: 2026-09-12 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5c2b6d2ff132"
down_revision: str | None = "e6dde395e1a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

choice_type_enum = postgresql.ENUM(
    "SKILL",
    "SPELL",
    "ABILITY_SCORE",
    "SAVING_THROW",
    "ARMOR",
    "WEAPON",
    name="choice_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE choice_type AS ENUM
                ('SKILL', 'SPELL', 'ABILITY_SCORE', 'SAVING_THROW', 'ARMOR', 'WEAPON');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.add_column("feature_choice_groups", sa.Column("choice_type", choice_type_enum, nullable=True))

    op.execute(
        """
        WITH group_type AS (
            SELECT g.id AS group_id,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM feature_choice_options o
                        JOIN feature_ability_score_effects e ON e.choice_option_id = o.id
                        WHERE o.group_id = g.id
                    ) THEN 'ABILITY_SCORE'
                    WHEN EXISTS (
                        SELECT 1 FROM feature_choice_options o
                        JOIN feature_skill_proficiency_effects e ON e.choice_option_id = o.id
                        WHERE o.group_id = g.id
                    ) THEN 'SKILL'
                    WHEN EXISTS (
                        SELECT 1 FROM feature_choice_options o
                        JOIN feature_saving_throw_effects e ON e.choice_option_id = o.id
                        WHERE o.group_id = g.id
                    ) THEN 'SAVING_THROW'
                    WHEN EXISTS (
                        SELECT 1 FROM feature_choice_options o
                        JOIN feature_armor_proficiency_effects e ON e.choice_option_id = o.id
                        WHERE o.group_id = g.id
                    ) THEN 'ARMOR'
                    WHEN EXISTS (
                        SELECT 1 FROM feature_choice_options o
                        JOIN feature_weapon_proficiency_effects e ON e.choice_option_id = o.id
                        WHERE o.group_id = g.id
                    ) THEN 'WEAPON'
                    WHEN EXISTS (
                        SELECT 1 FROM feature_choice_options o
                        JOIN feature_spell_grant_effects e ON e.choice_option_id = o.id
                        WHERE o.group_id = g.id
                    ) THEN 'SPELL'
                    ELSE 'SKILL'
                END AS choice_type
            FROM feature_choice_groups g
        )
        UPDATE feature_choice_groups
        SET choice_type = group_type.choice_type::choice_type
        FROM group_type
        WHERE feature_choice_groups.id = group_type.group_id;
        """
    )

    op.alter_column("feature_choice_groups", "choice_type", nullable=False)


def downgrade() -> None:
    op.drop_column("feature_choice_groups", "choice_type")
    op.execute("DROP TYPE IF EXISTS choice_type")
