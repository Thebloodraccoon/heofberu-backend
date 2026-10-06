# ORM models

SQLAlchemy 2.0 typed declarative models. `Base` (`app/settings/base.py`, also re-exported as `app.settings._common.Base`)
is a `DeclarativeBase` subclass; its `metadata` is what Alembic autogenerate and the test suite read.
The schema is owned by the Alembic migrations — a model change that alters DDL needs a migration, and
`tests/integration/core/test_migrations.py` fails on any drift between the models and the migrated database.

## Conventions for new models

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore
from app.models.enums import AbilityScoreType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.items.item_model import Item


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"), index=True)

    item: Mapped[Item | None] = relationship()
    parts: Mapped[list[Part]] = relationship(back_populates="widget", cascade="all, delete-orphan", passive_deletes=True)
```

* Every file starts with `from __future__ import annotations`; relationship targets that are not defined in the same
  file are imported under `TYPE_CHECKING` (they are resolved lazily through the registry, so no runtime import cycle).
* Nullability comes from the annotation: `Mapped[X]` is `NOT NULL`, `Mapped[X | None]` is nullable. Do not pass
  `nullable=` unless it must differ from the annotation (it never should).
* `int`, `bool` and a bare `str` (`VARCHAR` without length) are inferred; give the SQL type explicitly for everything
  else (`String(n)`, `Text`, `DateTime(timezone=True)`, `Numeric(p, s)`, `ARRAY(...)`, `JSONB`, `LtreeType`, `TSVECTOR`).
  Enum columns always pass the shared type from `app/models/enums.py` and are annotated with the domain enum
  (`Mapped[ArticleStatus]`).
* Relationships are annotated `Mapped[list[X]]` (collection), `Mapped[X]` (many-to-one on a NOT NULL FK) or
  `Mapped[X | None]` (nullable FK / `uselist=False` one-to-one). The target is taken from the annotation, so no string
  argument; strings are only used inside `order_by=`, `primaryjoin=` and `foreign_keys=`.
* Generated/lazy columns: `mapped_column(TSVECTOR, Computed(...), deferred=True)`.
* Indexes, check constraints and unique constraints stay in `__table_args__` (named explicitly); functional or
  partial indexes that need the mapped class go after the class body (`Index("...", func.lower(Tag.name), unique=True)`).
* Pure association tables with no payload remain Core `Table(..., Base.metadata, Column(...))` objects (referenced as
  `secondary=`); tables with extra columns or their own constraints are mapped classes.
* `__repr__(self) -> str`, kept short; never trigger lazy loads in it.
* Register new modules in `app/models/__init__.py` so `Base.metadata` sees them.
