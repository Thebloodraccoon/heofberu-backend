"""Update class with hit dice enum

Revision ID: ed896a68cda0
Revises: 5bde518ea704
Create Date: 2026-07-31 18:45:33.978615

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ed896a68cda0"
down_revision: Union[str, None] = "5bde518ea704"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


hit_dice_enum = sa.Enum("D4", "D6", "D8", "D10", "D12", "D20", "D100", name="hit_dice")


def upgrade() -> None:
    """Upgrade schema."""
    # Native Postgres ENUM type must exist before it can be used as a
    # column type — autogenerate doesn't add this CREATE TYPE step itself.
    hit_dice_enum.create(op.get_bind(), checkfirst=True)

    op.alter_column(
        "classes",
        "hit_dice",
        existing_type=sa.VARCHAR(length=10),
        type_=hit_dice_enum,
        existing_nullable=False,
        postgresql_using="hit_dice::hit_dice",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "classes", "hit_dice", existing_type=hit_dice_enum, type_=sa.VARCHAR(length=10), existing_nullable=False
    )

    hit_dice_enum.drop(op.get_bind(), checkfirst=True)
