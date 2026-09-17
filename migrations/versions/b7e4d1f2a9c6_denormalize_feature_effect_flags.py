"""denormalize features.has_static_effects / has_choices

Both were plain ``Feature`` properties computed on read from the six
fixed-effect relationships / ``choice_groups`` — cheap once the tree is
eager-loaded, but ``GET /features``/``GET /feats`` listings had to run
``load_effect_flags`` (one ``SELECT DISTINCT`` per effect type, 7 queries)
on every cache miss just to get these two booleans. Turning them into real
columns lets those listings column-select them directly; every write path
that touches a feature's effects/choice groups now maintains the columns
itself (``FeatureEffectsService.set_fixed_effects``/``set_choice_groups``,
``FeatRepository.set_ability_score_increases``) instead of the flags being
computed post-hoc.

Backfill runs once at migration time from the current effect/choice-group
rows; after that, application code is the only writer.

Revision ID: b7e4d1f2a9c6
Revises: c2a4e8f1b6d3
Create Date: 2026-09-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e4d1f2a9c6"
down_revision: Union[str, None] = "c2a4e8f1b6d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The six fixed-effect tables `has_static_effects` checks (mirrors
# `_STATIC_EFFECT_MODELS` in app/features/features/crud/repository.py).
_STATIC_EFFECT_TABLES = (
    "feature_ability_score_effects",
    "feature_skill_proficiency_effects",
    "feature_saving_throw_effects",
    "feature_armor_proficiency_effects",
    "feature_weapon_proficiency_effects",
    "feature_spell_grant_effects",
)


def upgrade() -> None:
    op.add_column(
        "features",
        sa.Column("has_static_effects", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "features",
        sa.Column("has_choices", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    static_effects_exists = " OR ".join(
        f"EXISTS (SELECT 1 FROM {table} WHERE {table}.feature_id = features.id)"
        for table in _STATIC_EFFECT_TABLES
    )
    op.execute(f"UPDATE features SET has_static_effects = TRUE WHERE {static_effects_exists}")
    op.execute(
        "UPDATE features SET has_choices = TRUE "
        "WHERE EXISTS (SELECT 1 FROM feature_choice_groups WHERE feature_choice_groups.feature_id = features.id)"
    )


def downgrade() -> None:
    op.drop_column("features", "has_choices")
    op.drop_column("features", "has_static_effects")
