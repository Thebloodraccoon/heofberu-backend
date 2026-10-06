"""Resync primary-key sequences

The seed scripts insert rows with explicit ``id`` values into the
reference tables (skills, races, classes, backgrounds, feats, features,
spells), which does NOT advance their ``*_id_seq`` sequences. As a
result, the next app-inserted row collides with an existing primary key:
``duplicate key value violates unique constraint "<table>_pkey"``
(``Key (id)=(N) already exists``), surfaced by the API as
"Record with this data already exists".

Fix: for every serial/identity sequence owned by a table column in the
current schema, set its value to ``MAX(column)`` so the next
``nextval()`` returns ``MAX(column) + 1``. Idempotent and safe on fresh
schemas (no sequences yet).

Revision ID: f1a2b3c4d5e6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-10 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RESYNC_SEQUENCES = """
DO $$
DECLARE
    r RECORD;
    max_id BIGINT;
BEGIN
    FOR r IN
        SELECT n.nspname AS schema_name,
               t.relname AS table_name,
               s.relname AS seq_name,
               a.attname AS column_name
        FROM pg_class s
        JOIN pg_depend d
          ON d.objid = s.oid
         AND d.classid = 'pg_class'::regclass
         AND d.refclassid = 'pg_class'::regclass
        JOIN pg_class t
          ON t.oid = d.refobjid
        JOIN pg_attribute a
          ON a.attrelid = t.oid
         AND a.attnum = d.refobjsubid
        JOIN pg_namespace n
          ON n.oid = s.relnamespace
        WHERE s.relkind = 'S'
          AND n.nspname = current_schema()
          AND d.deptype IN ('a', 'i')
    LOOP
        EXECUTE format('SELECT COALESCE(MAX(%I), 1) FROM %I.%I',
                       r.column_name, r.schema_name, r.table_name)
        INTO max_id;
        EXECUTE format('SELECT setval(%L, %s)', r.seq_name, max_id);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(_RESYNC_SEQUENCES)


def downgrade() -> None:
    """Downgrade schema.

    Non-reversible: there is no safe way to restore a deliberately
    desynced sequence.
    """
    pass
