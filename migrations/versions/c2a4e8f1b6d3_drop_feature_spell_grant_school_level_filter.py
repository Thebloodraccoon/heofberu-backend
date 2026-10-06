"""
drop spell_school and spell_level_max from feature_spell_grant_effects

Both filter columns constrained an "open" spell choice (spell_id IS NULL) to
a school and/or a max level, but that filtering was never actually used by
any real catalog content. Dropping them: an open spell choice now always
lets the player pick any spell from the catalog, unconstrained. Concrete
(spell_id set) spell grants are unaffected.

Revision ID: c2a4e8f1b6d3
Revises: 76676c656c28
Create Date: 2026-09-16 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2a4e8f1b6d3"
down_revision: str | None = "76676c656c28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

spell_level_enum = postgresql.ENUM(
    "CANTRIP",
    "LEVEL_1",
    "LEVEL_2",
    "LEVEL_3",
    "LEVEL_4",
    "LEVEL_5",
    "LEVEL_6",
    "LEVEL_7",
    "LEVEL_8",
    "LEVEL_9",
    name="spell_level",
    create_type=False,
)
spell_school_enum = postgresql.ENUM(
    "ABJURATION",
    "CONJURATION",
    "DIVINATION",
    "ENCHANTMENT",
    "EVOCATION",
    "ILLUSION",
    "NECROMANCY",
    "TRANSMUTATION",
    name="spell_school",
    create_type=False,
)


def upgrade() -> None:
    """Drop the school/level-max filter columns and their now-vacuous check constraint."""
    op.drop_constraint("ck_feature_spell_grant_effect_specific_or_filter", "feature_spell_grant_effects", type_="check")
    op.drop_column("feature_spell_grant_effects", "spell_school")
    op.drop_column("feature_spell_grant_effects", "spell_level_max")


def downgrade() -> None:
    """Restore the two filter columns and their guard constraint."""
    op.add_column("feature_spell_grant_effects", sa.Column("spell_level_max", spell_level_enum, nullable=True))
    op.add_column("feature_spell_grant_effects", sa.Column("spell_school", spell_school_enum, nullable=True))
    op.create_check_constraint(
        "ck_feature_spell_grant_effect_specific_or_filter",
        "feature_spell_grant_effects",
        "(spell_id IS NOT NULL AND spell_school IS NULL AND spell_level_max IS NULL) OR (spell_id IS NULL)",
    )
