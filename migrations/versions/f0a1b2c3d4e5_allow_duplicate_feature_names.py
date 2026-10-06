"""Allow duplicate feature names

Drop the stale UNIQUE constraint/index on ``features.name`` that was left
over from an older schema (the current model and migrations declare the
``name`` column as non-unique) and recreate the plain search index. After
this migration, adding a feature whose name already exists no longer fails.

Revision ID: f0a1b2c3d4e5
Revises: a1b2c3d4e5f7
Create Date: 2026-08-10 10:20:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The exact leftover object in the deployed DB is unknown, so drop it by
# introspection:
#   1. any UNIQUE constraint covering features.name (drops its backing index);
#   2. any remaining unique index covering features.name (e.g. ix_features_name
#      created as a unique index by an older model with ``unique=True``).
# Then (re)create the plain non-unique search index idempotently so the
# migration is also a no-op on a fresh schema.
_DROP_UNIQUE = """
DO $$
DECLARE
    con_name text;
    idx_name text;
BEGIN
    FOR con_name IN
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = current_schema()
          AND t.relname = 'features'
          AND c.contype = 'u'
          AND EXISTS (
              SELECT 1
              FROM unnest(c.conkey::smallint[]) AS k(attnum)
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
              WHERE a.attname = 'name'
          )
    LOOP
        EXECUTE format('ALTER TABLE features DROP CONSTRAINT %I', con_name);
    END LOOP;

    FOR idx_name IN
        SELECT i.relname
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        LEFT JOIN pg_constraint c ON c.conindid = i.oid AND c.contype = 'u'
        WHERE n.nspname = current_schema()
          AND t.relname = 'features'
          AND x.indisunique
          AND c.conindid IS NULL
          AND EXISTS (
              SELECT 1
              FROM unnest(x.indkey::smallint[]) AS k(attnum)
              JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum
              WHERE a.attname = 'name'
          )
    LOOP
        EXECUTE format('DROP INDEX %I', idx_name);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(_DROP_UNIQUE)
    op.execute("CREATE INDEX IF NOT EXISTS ix_features_name ON features (name)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_features_name")
    op.execute("CREATE UNIQUE INDEX ix_features_name ON features (name)")
