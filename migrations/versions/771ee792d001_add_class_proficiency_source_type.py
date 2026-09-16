"""add CLASS to proficiency_source_type

While wiring the character-creation/rebuild flows onto the unified
``character_proficiencies`` table, class-granted saving throws (the class's
fixed ``saving_throws`` list — no player choice involved, not yet routed
through the feature engine) turned out to have no matching
``ProficiencySourceType`` value: ``CLASS_CHOICE`` is specifically the
player's skill pick, not a fit. Adds ``CLASS`` alongside it, mirroring the
existing no-choice ``RACE``/``BACKGROUND`` values.

Postgres can't drop an enum value, so ``downgrade()`` is a no-op — the
value stays in the type (same precedent as ``FeatureSourceType.FEAT``).

Revision ID: 771ee792d001
Revises: f0168d7c8559
Create Date: 2026-09-11 19:45:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "771ee792d001"
down_revision: Union[str, None] = "f0168d7c8559"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE proficiency_source_type ADD VALUE IF NOT EXISTS 'CLASS'")


def downgrade() -> None:
    # Postgres cannot drop an enum value; the value simply stays unused.
    pass
