"""Fix role constraint to gm/player and seed default GM user

Revision ID: 0003_add_default_gm
Revises: 0002_initial_schema
Create Date: 2025-07-25 00:00:00.000000

"""

import os
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from passlib.context import CryptContext

# revision identifiers, used by Alembic.
revision: str = "0003_add_default_gm"
down_revision: Union[str, None] = "0002_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

users_table = sa.table(
    "users",
    sa.column("username", sa.String),
    sa.column("email", sa.String),
    sa.column("hashed_password", sa.String),
    sa.column("role", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    """Fix stale role constraint (found_father/keeper/player -> gm/player) and seed default GM."""

    # --- fix check constraint: old roles no longer exist ---
    op.drop_constraint("check_user_role", "users", type_="check")
    op.create_check_constraint(
        "check_user_role",
        "users",
        "role IN ('gm', 'player')",
    )

    # --- seed default GM user from env vars (required, no silent fallback) ---
    admin_name = os.getenv("ADMIN_NAME")
    admin_login = os.getenv("ADMIN_LOGIN")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_login or not admin_password:
        raise RuntimeError("ADMIN_LOGIN and ADMIN_PASSWORD environment variables are required to run this migration.")

    hashed_password = pwd_context.hash(admin_password)
    now = datetime.now(timezone.utc)

    op.bulk_insert(
        users_table,
        [
            {
                "username": admin_name,
                "email": admin_login,
                "hashed_password": hashed_password,
                "role": "gm",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    """Remove default GM user and revert role constraint."""

    op.execute("DELETE FROM users WHERE email = :email", {"email": os.getenv("ADMIN_LOGIN", "")})

    op.drop_constraint("check_user_role", "users", type_="check")
    op.create_check_constraint(
        "check_user_role",
        "users",
        "role IN ('found_father', 'keeper', 'player')",
    )
