from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy import Column
from sqlalchemy.orm import Session


class ModelProtocol(Protocol):
    """Protocol for determining the basic attributes of the model."""

    id: Column[int]


ModelType = TypeVar("ModelType", bound=ModelProtocol)


class BaseRepository(Generic[ModelType]):
    """
    Base repository providing common CRUD operations for SQLAlchemy models.

    ``BaseRepository`` wraps the plain SQLAlchemy ``Session`` query calls
    needed for standard CRUD access, so that a feature repository only
    needs to supply its model. Feature-specific queries (custom ordering,
    lookups by a unique field, joins, etc.) are added by subclassing and
    extending or overriding the methods below — the base class covers the
    plain CRUD case, not every case.

    Type parameters:
        ModelType: The SQLAlchemy model this repository operates on. Must
            satisfy ``ModelProtocol``, i.e. expose an ``id`` column, since
            every base method that targets a single record does so by ID.

    Example:
        Wiring the base class into a concrete feature repository::

            class SpellRepository(BaseRepository[Spell]):
                def __init__(self, db: Session):
                    super().__init__(Spell, db)

                def get_by_name(self, name: str) -> Spell | None:
                    return self.db.query(Spell).filter(Spell.name == name).first()

        A subclass can also override or extend the base methods for
        feature-specific needs — e.g. adding a custom-ordered listing on
        top of :meth:`get_all_brief` — but should not override
        :meth:`get_all` itself to skip pagination; the base contract
        (always paginated) is relied on by :class:`BaseService`.

    """

    def __init__(self, model: type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get_by_id(self, model_id: int) -> ModelType | None:
        """Retrieve a single record by its primary key ID, or ``None`` if missing."""

        return self.db.query(self.model).filter(self.model.id == model_id).first()

    def get_all(self, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """
        Retrieve multiple records with offset-based pagination.

        This is always paginated — feature repositories should not
        override it to return a full list. Use :meth:`get_all_brief` for
        a quick, unpaginated listing of specific columns instead.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        """

        return self.db.query(self.model).offset(skip).limit(limit).all()

    def get_all_brief(self, *columns: Any) -> list[Any]:
        """
        Retrieve every record as lightweight rows of the given columns.

        Unlike :meth:`get_all`, this is not paginated (intended for quick,
        low-cost listing queries) and does not load full model instances:
        the caller selects exactly which columns to fetch, and each result
        is a SQLAlchemy ``Row``/tuple of those columns rather than a
        ``ModelType`` instance.

        Args:
            *columns: The model columns to select, e.g.
                ``repository.get_all_brief(Spell.id, Spell.name)``. At
                least one column must be given.

        Returns:
            A list of ``Row`` tuples, one per record, in column order.

        """

        return self.db.query(*columns).all()

    def count_all(self) -> int:
        """Count the total number of records in the table."""

        return self.db.query(self.model).count()

    def create(self, obj_data: dict[str, Any]) -> ModelType:
        """
        Create a new record from ``obj_data`` and return it, refreshed from the DB.

        ``obj_data`` is passed as keyword arguments to the model's
        constructor, so its keys must match the model's column/attribute
        names (this is how ``BaseService.create`` feeds it a schema's
        ``model_dump()`` output).
        """

        db_obj = self.model(**obj_data)

        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)

        return db_obj

    def update(self, db_obj: ModelType, update_data: dict[str, Any]) -> ModelType:
        """
        Apply ``update_data`` onto an existing record and return it, refreshed.

        Only keys that already exist as attributes on ``db_obj`` are set
        (via ``hasattr``); unknown keys are silently ignored rather than
        raising, so callers should validate field names upstream (e.g.
        through a Pydantic update schema) if stricter behaviour is needed.
        """

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        self.db.commit()
        self.db.refresh(db_obj)

        return db_obj

    def delete(self, db_obj: ModelType) -> bool:
        """Delete ``db_obj`` from the database, returning ``True`` on success."""

        self.db.delete(db_obj)
        self.db.commit()

        return True

    def exists_by_id(self, model_id: int) -> bool:
        """Return whether a record with ``model_id`` exists, without loading it."""

        return self.db.query(self.model).filter(self.model.id == model_id).first() is not None

    def filter_by_fields(self, **filters) -> list[ModelType]:
        """
        Filter records by exact matches on one or more fields.

        Only keyword arguments that correspond to actual model attributes
        and are not ``None`` are turned into filter conditions; ``None``
        values are treated as "no filter on this field" rather than
        "field IS NULL", so this method isn't suitable for querying nulls.
        """

        query = self.db.query(self.model)
        for field, value in filters.items():
            if hasattr(self.model, field) and value is not None:
                query = query.filter(getattr(self.model, field) == value)

        return query.all()
