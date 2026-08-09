"""add new role of user

Revision ID: 8e6cbf5381ba
Revises: d4c1e9b2a7f3
Create Date: 2026-08-08 13:18:56.624162

"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8e6cbf5381ba"
down_revision: Union[str, None] = "d4c1e9b2a7f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Alembic уже открыл транзакцию — закрываем её вручную,
    # иначе ALTER TYPE ADD VALUE нельзя закоммитить отдельно.
    bind.execute(sa.text("COMMIT"))

    bind.execute(sa.text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'FOUND_FATHER'"))

    # Открываем новую транзакцию для остального DDL/DML
    bind.execute(sa.text("BEGIN"))

    op.create_unique_constraint("uq_character_feat", "character_feats", ["character_id", "feat_id"])

    admin_login = os.getenv("ADMIN_LOGIN")
    if admin_login:
        op.execute(sa.text("UPDATE users SET role = 'FOUND_FATHER' WHERE email = :email").bindparams(email=admin_login))


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE, so the FOUND_FATHER enum
    # value stays; only the admin promotion is reverted.
    admin_login = os.getenv("ADMIN_LOGIN")
    if admin_login:
        op.execute(sa.text("UPDATE users SET role = 'GM' WHERE email = :email").bindparams(email=admin_login))

    op.drop_constraint("uq_character_feat", "character_feats", type_="unique")
