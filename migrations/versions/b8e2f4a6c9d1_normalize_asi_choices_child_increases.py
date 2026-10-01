"""normalize character_asi_choices: child increases table + applied_to_base flag

Upgrade: the untyped ``increases`` JSONB (``[{"ability": "STR", "amount": 2}, ...]``) is expanded into typed child
rows. Rules for the expansion (the JSONB column is dropped afterwards, so nothing is skipped silently):

* SQL NULL, JSON ``null`` and non-array payloads mean "no increases".
* An ability repeated inside one array is SUMmed into one row (``UNIQUE (choice, ability)``).
* ``ability`` is matched case-insensitively against the ``ability_score`` enum, ``amount`` must be an integer
  (number or numeric string). A malformed element aborts the migration with its choice id and payload instead of
  being dropped; fix or remove it and run ``alembic upgrade head`` again.

All pre-existing rows get ``applied_to_base = TRUE`` (their points are already in the base ability columns).

Downgrade is lossless for the points: increments of rows with ``applied_to_base = FALSE`` (written after this
revision, never folded into the base columns) are added onto ``characters.strength`` ... ``charisma`` first, because
the old code reads only the base columns; then the JSONB payload is rebuilt for every choice. What is still lost:
duplicates merged on upgrade stay merged, the cached ``character_ability_scores`` rows are not touched (they already
include these points, so they stay correct), and a base score can exceed the usual cap of 30 if the GM stacked points.

Revision ID: b8e2f4a6c9d1
Revises: f9c6d8e2b4a7
Create Date: 2026-08-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8e2f4a6c9d1"
down_revision: Union[str, None] = "f9c6d8e2b4a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ability_score_enum = postgresql.ENUM(
    "STR",
    "DEX",
    "CON",
    "INT",
    "WIS",
    "CHA",
    name="ability_score",
    create_type=False,
)


_ABILITY_LABELS = "'STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'"

#: One row per element of every array payload (other payload shapes yield no rows).
_LEGACY_ENTRIES_SQL = """
    SELECT c.id AS choice_id, entry
    FROM character_asi_choices c,
         jsonb_array_elements(
             CASE WHEN jsonb_typeof(c.increases) = 'array' THEN c.increases ELSE '[]'::jsonb END
         ) AS entry
"""


def _reject_malformed_payloads() -> None:
    """Abort, naming the offenders, when a payload element cannot become a typed row."""

    rows = (
        op.get_bind()
        .execute(
            sa.text(
                f"""
                SELECT choice_id, entry::text AS entry FROM ({_LEGACY_ENTRIES_SQL}) AS legacy
                WHERE NOT COALESCE(
                    jsonb_typeof(entry) = 'object'
                    AND upper(entry->>'ability') IN ({_ABILITY_LABELS})
                    AND (entry->>'amount') ~ '^-?[0-9]{{1,9}}$',
                    FALSE
                )
                ORDER BY choice_id
                """
            )
        )
        .all()
    )
    if rows:
        shown = "; ".join(f"choice {row.choice_id}: {row.entry}" for row in rows[:20])
        raise RuntimeError(
            f"{len(rows)} element(s) of character_asi_choices.increases are not {{ability, amount}} objects with a "
            f"known ability and an integer amount ({shown}). Fix or remove them, then run the migration again."
        )


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Child table holding the counted increments of each ASI choice
    #    (replaces the untyped `increases` JSONB column).
    op.create_table(
        "character_asi_choice_increases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_asi_choice_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["character_asi_choice_id"],
            ["character_asi_choices.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_asi_choice_id", "ability", name="uq_character_asi_inc_ability"),
    )
    op.create_index(
        op.f("ix_character_asi_choice_increases_character_asi_choice_id"),
        "character_asi_choice_increases",
        ["character_asi_choice_id"],
        unique=False,
    )

    # 2. Grandfather flag: every EXISTING choice had its points applied
    #    straight onto the base ability columns by the old code paths
    #    (level-up ASI bumps and GM ±adjustments), so all of them must be
    #    excluded from the calculator to avoid double counting. The column
    #    is added with a TRUE default so every existing row flips to True,
    #    then the default is switched to FALSE — matching the model — for
    #    all rows written from now on.
    op.add_column(
        "character_asi_choices",
        sa.Column("applied_to_base", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column(
        "character_asi_choices",
        "applied_to_base",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
    )

    # 3. Expand the legacy JSONB payloads into typed child rows so the
    #    audit data survives the (later) column drop; the rows stay
    #    grandfathered via the flag above.
    _reject_malformed_payloads()
    op.execute(
        f"""
        INSERT INTO character_asi_choice_increases (character_asi_choice_id, ability, amount)
        SELECT choice_id, upper(entry->>'ability')::ability_score, SUM((entry->>'amount')::integer)
        FROM ({_LEGACY_ENTRIES_SQL}) AS legacy
        GROUP BY choice_id, upper(entry->>'ability')
        """
    )

    # 4. Drop the JSONB payload — the child rows are the source now.
    op.drop_column("character_asi_choices", "increases")


def downgrade() -> None:
    """Downgrade schema."""

    # Rows written after the upgrade (applied_to_base = FALSE) were counted by the calculator from the child
    # rows only; the old code reads the base columns alone, so fold their points into them first.
    op.execute(
        """
        UPDATE characters ch
        SET strength = ch.strength + COALESCE(t.str, 0),
            dexterity = ch.dexterity + COALESCE(t.dex, 0),
            constitution = ch.constitution + COALESCE(t.con, 0),
            intelligence = ch.intelligence + COALESCE(t.int, 0),
            wisdom = ch.wisdom + COALESCE(t.wis, 0),
            charisma = ch.charisma + COALESCE(t.cha, 0)
        FROM (
            SELECT c.character_id,
                   SUM(i.amount) FILTER (WHERE i.ability = 'STR') AS str,
                   SUM(i.amount) FILTER (WHERE i.ability = 'DEX') AS dex,
                   SUM(i.amount) FILTER (WHERE i.ability = 'CON') AS con,
                   SUM(i.amount) FILTER (WHERE i.ability = 'INT') AS int,
                   SUM(i.amount) FILTER (WHERE i.ability = 'WIS') AS wis,
                   SUM(i.amount) FILTER (WHERE i.ability = 'CHA') AS cha
            FROM character_asi_choice_increases i
            JOIN character_asi_choices c ON c.id = i.character_asi_choice_id
            WHERE c.applied_to_base = FALSE
            GROUP BY c.character_id
        ) AS t
        WHERE ch.id = t.character_id
        """
    )

    # Rebuild the legacy JSONB payloads from the child rows before
    # dropping them (grandfathered or not — data is data).
    op.add_column(
        "character_asi_choices",
        sa.Column("increases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE character_asi_choices c
        SET increases = rebuilt.payload
        FROM (
            SELECT character_asi_choice_id,
                   jsonb_agg(jsonb_build_object('ability', ability::text, 'amount', amount)) AS payload
            FROM character_asi_choice_increases
            GROUP BY character_asi_choice_id
        ) AS rebuilt
        WHERE c.id = rebuilt.character_asi_choice_id
        """
    )

    op.drop_column("character_asi_choices", "applied_to_base")
    op.drop_index(
        op.f("ix_character_asi_choice_increases_character_asi_choice_id"),
        table_name="character_asi_choice_increases",
    )
    op.drop_table("character_asi_choice_increases")
