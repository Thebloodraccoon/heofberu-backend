from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7e70b8a81bb9"
down_revision: Union[str, None] = "ad86e093f8cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


spell_component_enum = postgresql.ENUM("VERBAL", "SOMATIC", "MATERIAL", name="spell_component")


def upgrade() -> None:
    """Upgrade schema."""
    spell_component_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "spells",
        sa.Column(
            "components",
            sa.ARRAY(sa.Enum("VERBAL", "SOMATIC", "MATERIAL", name="spell_component", create_type=False)),
            nullable=False,
            server_default="{}",
        ),
    )

    op.alter_column("spells", "components", server_default=None)
    op.drop_column("spells", "has_somatic")
    op.drop_column("spells", "has_material")
    op.drop_column("spells", "has_verbal")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("spells", sa.Column("has_verbal", sa.BOOLEAN(), autoincrement=False, nullable=False))
    op.add_column("spells", sa.Column("has_material", sa.BOOLEAN(), autoincrement=False, nullable=False))
    op.add_column("spells", sa.Column("has_somatic", sa.BOOLEAN(), autoincrement=False, nullable=False))
    op.drop_column("spells", "components")

    spell_component_enum.drop(op.get_bind(), checkfirst=True)
