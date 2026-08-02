"""Convert spells.cast_time and spells.duration to native enums

Revision ID: xxxxxxxxxxxx
Revises: 7e70b8a81bb9
Create Date: 2026-08-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "xxxxxxxxxxxx"
down_revision: Union[str, None] = "7e70b8a81bb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


spell_cast_time_enum = postgresql.ENUM(
    "ACTION",
    "BONUS_ACTION",
    "REACTION",
    "SPECIAL",
    name="spell_cast_time",
)

spell_duration_enum = postgresql.ENUM(
    "INSTANTANEOUS",
    "ONE_ROUND",
    "ONE_MINUTE",
    "TEN_MINUTES",
    "ONE_HOUR",
    "EIGHT_HOURS",
    "TWENTY_FOUR_HOURS",
    "SEVEN_DAYS",
    "THIRTY_DAYS",
    "UNTIL_DISPELLED",
    "SPECIAL",
    name="spell_duration",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    spell_cast_time_enum.create(bind, checkfirst=True)
    spell_duration_enum.create(bind, checkfirst=True)

    op.add_column(
        "spells",
        sa.Column(
            "cast_time_new",
            sa.Enum(
                "ACTION",
                "BONUS_ACTION",
                "REACTION",
                "SPECIAL",
                name="spell_cast_time",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "spells",
        sa.Column(
            "duration_new",
            sa.Enum(
                "INSTANTANEOUS",
                "ONE_ROUND",
                "ONE_MINUTE",
                "TEN_MINUTES",
                "ONE_HOUR",
                "EIGHT_HOURS",
                "TWENTY_FOUR_HOURS",
                "SEVEN_DAYS",
                "THIRTY_DAYS",
                "UNTIL_DISPELLED",
                "SPECIAL",
                name="spell_duration",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    op.execute("""
        UPDATE spells SET cast_time_new = CASE cast_time
            WHEN '1 action' THEN 'ACTION'
            WHEN '1 bonus action' THEN 'BONUS_ACTION'
            WHEN '1 reaction' THEN 'REACTION'
            ELSE 'SPECIAL'
        END::spell_cast_time
    """)

    op.execute("""
        UPDATE spells SET duration_new = CASE duration
            WHEN 'Instantaneous' THEN 'INSTANTANEOUS'
            WHEN '1 round' THEN 'ONE_ROUND'
            WHEN '1 minute' THEN 'ONE_MINUTE'
            WHEN 'Concentration, up to 1 minute' THEN 'ONE_MINUTE'
            WHEN 'Concentration, up to 10 minutes' THEN 'TEN_MINUTES'
            WHEN '1 hour' THEN 'ONE_HOUR'
            WHEN 'Concentration, up to 1 hour' THEN 'ONE_HOUR'
            ELSE 'SPECIAL'
        END::spell_duration
    """)

    op.drop_column("spells", "cast_time")
    op.drop_column("spells", "duration")
    op.alter_column("spells", "cast_time_new", new_column_name="cast_time")
    op.alter_column("spells", "duration_new", new_column_name="duration")
    op.alter_column("spells", "cast_time", nullable=False)
    op.alter_column("spells", "duration", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column("spells", sa.Column("cast_time_old", sa.String(length=50), nullable=True))
    op.add_column("spells", sa.Column("duration_old", sa.String(length=50), nullable=True))

    op.execute("""
        UPDATE spells SET cast_time_old = CASE cast_time
            WHEN 'ACTION' THEN '1 action'
            WHEN 'BONUS_ACTION' THEN '1 bonus action'
            WHEN 'REACTION' THEN '1 reaction'
            ELSE 'Special'
        END
    """)
    op.execute("""
        UPDATE spells SET duration_old = CASE duration
            WHEN 'INSTANTANEOUS' THEN 'Instantaneous'
            WHEN 'ONE_ROUND' THEN '1 round'
            WHEN 'ONE_MINUTE' THEN '1 minute'
            WHEN 'TEN_MINUTES' THEN '10 minutes'
            WHEN 'ONE_HOUR' THEN '1 hour'
            WHEN 'EIGHT_HOURS' THEN '8 hours'
            WHEN 'TWENTY_FOUR_HOURS' THEN '24 hours'
            WHEN 'SEVEN_DAYS' THEN '7 days'
            WHEN 'THIRTY_DAYS' THEN '30 days'
            WHEN 'UNTIL_DISPELLED' THEN 'Until dispelled'
            ELSE 'Special'
        END
    """)

    op.drop_column("spells", "cast_time")
    op.drop_column("spells", "duration")

    op.alter_column("spells", "cast_time_old", new_column_name="cast_time")
    op.alter_column("spells", "duration_old", new_column_name="duration")
    op.alter_column("spells", "cast_time", nullable=False)
    op.alter_column("spells", "duration", nullable=False)

    spell_cast_time_enum.drop(op.get_bind(), checkfirst=True)
    spell_duration_enum.drop(op.get_bind(), checkfirst=True)
