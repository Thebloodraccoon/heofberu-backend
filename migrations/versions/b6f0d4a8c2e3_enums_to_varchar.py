"""native ENUMs -> VARCHAR: user_role, spell_cast_time, spell_duration, item_type

These sets grow with content/product decisions, and a native ENUM value can't be removed
(``ALTER TYPE ... ADD VALUE`` only, with transaction caveats). The columns become VARCHAR
holding the same member NAMES (``USING col::text`` — no data change), validated in Python
(``SAEnum(native_enum=False)``). ``users.role`` keeps a DB CHECK (``ck_users_role``) because
it gates permissions.

New ``SpellCastTime`` members (ONE_MINUTE ... TWENTY_FOUR_HOURS) need no DB change; the
downgrade folds them back into SPECIAL.

Revision ID: b6f0d4a8c2e3
Revises: a5e9c3f7b1d2
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6f0d4a8c2e3"
down_revision: Union[str, None] = "a5e9c3f7b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (table, column, enum type, VARCHAR length, labels as they were in the native type)
COLUMNS = [
    ("users", "role", "user_role", 20, ["GM", "PLAYER", "FOUND_FATHER"]),
    ("spells", "cast_time", "spell_cast_time", 30, ["ACTION", "BONUS_ACTION", "REACTION", "SPECIAL"]),
    (
        "spells",
        "duration",
        "spell_duration",
        30,
        [
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
        ],
    ),
    (
        "items",
        "item_type",
        "item_type",
        30,
        [
            "WEAPON",
            "ARMOR",
            "SHIELD",
            "POTION",
            "SCROLL",
            "WONDROUS_ITEM",
            "RING",
            "ROD",
            "STAFF",
            "WAND",
            "ADVENTURING_GEAR",
            "TOOL",
            "AMMUNITION",
            "TREASURE",
            "OTHER",
        ],
    ),
]


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_user_role")

    for table, column, type_name, length, _ in COLUMNS:
        op.alter_column(table, column, type_=sa.String(length), postgresql_using=f"{column}::text")
        op.execute(f"DROP TYPE {type_name}")

    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'PLAYER'")
    op.create_check_constraint("ck_users_role", "users", "role IN ('GM', 'PLAYER', 'FOUND_FATHER')")


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute(
        "UPDATE spells SET cast_time = 'SPECIAL' "
        "WHERE cast_time NOT IN ('ACTION', 'BONUS_ACTION', 'REACTION', 'SPECIAL')"
    )

    for table, column, type_name, _, labels in COLUMNS:
        values = ", ".join(f"'{label}'" for label in labels)
        op.execute(f"CREATE TYPE {type_name} AS ENUM ({values})")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_name} USING {column}::{type_name}")

    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'PLAYER'")
