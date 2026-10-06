"""Install PostgreSQL extensions

Revision ID: 0001_install_extensions
Revises:
Create Date: 2025-06-11 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_install_extensions"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Install required PostgreSQL extensions."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin;")


def downgrade() -> None:
    """Remove PostgreSQL extensions."""
    op.execute("DROP EXTENSION IF EXISTS btree_gin;")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
