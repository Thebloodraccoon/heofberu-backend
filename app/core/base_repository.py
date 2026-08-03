from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy import String, Text, inspect, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import RecordAlreadyExistsError


class ModelProtocol(Protocol):
    """Protocol for determining the basic attributes of the model."""

    id: Any


ModelType = TypeVar("ModelType", bound=ModelProtocol)


class BaseRepository(Generic[ModelType]):
    """
    Common CRUD operations for SQLAlchemy models.

    Subclass and supply ``model`` for the plain CRUD case; override or
    extend methods for feature-specific queries.

    Args:
        model: SQLAlchemy model, must expose ``id``.
        db: Active session.
        default_load_options: Loader options (``selectinload``,
            ``joinedload``, ...) applied automatically on
            :meth:`get_by_id`/:meth:`get_all`, for relationships the
            response schema always includes.
        search_fields: Columns used by :meth:`_apply_search`. Defaults to
            auto-detected ``String``/``Text`` columns; pass ``[]`` to
            disable search.
        unique_fields: Columns checked by :meth:`_check_uniqueness` on
            create/update.

    Example::

        class SpellRepository(BaseRepository[Spell]):
            def __init__(self, db: Session):
                super().__init__(Spell, db)
    """

    def __init__(
        self,
        model: type[ModelType],
        db: Session,
        default_load_options: list[Any] | None = None,
        search_fields: list[str] | None = None,
        unique_fields: list[str] | None = None,
    ):
        self.model = model
        self.db = db
        self._default_load_options = default_load_options or []
        self._search_fields = search_fields if search_fields is not None else self._detect_text_fields()
        self._unique_fields = unique_fields or []

    def _detect_text_fields(self) -> list[str]:
        """Auto-detect ``String``/``Text`` column names on ``self.model``."""

        mapper = inspect(self.model)
        return [column.key for column in mapper.columns if isinstance(column.type, String | Text)]

    def _apply_filters(self, query: Any, filters: dict[str, Any] | None) -> Any:
        """Apply exact-match, AND'd filters for known, non-``None`` keys in ``filters``."""

        if not filters:
            return query

        for field, value in filters.items():
            if hasattr(self.model, field) and value is not None:
                query = query.filter(getattr(self.model, field) == value)

        return query

    def _apply_search(self, query: Any, search: str | None) -> Any:
        """Apply a case-insensitive ``ILIKE`` substring match, OR'd across ``self._search_fields``."""

        if not search or not self._search_fields:
            return query

        conditions = [
            getattr(self.model, field).ilike(f"%{search}%")
            for field in self._search_fields
            if hasattr(self.model, field)
        ]

        if not conditions:
            return query

        return query.filter(or_(*conditions))

    def get_by_id(self, model_id: int) -> ModelType | None:
        """Retrieve a single record by ID, or ``None`` if missing. Applies ``default_load_options``."""

        query = self.db.query(self.model)
        if self._default_load_options:
            query = query.options(*self._default_load_options)

        return query.filter(self.model.id == model_id).first()

    def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> list[ModelType]:
        """
        Retrieve records with offset-based pagination, ordered by ``id``.

        Applies ``default_load_options``, ``filters`` (exact-match, AND'd),
        and ``search`` (substring, OR'd across search fields).
        """

        query = self.db.query(self.model)
        if self._default_load_options:
            query = query.options(*self._default_load_options)

        query = self._apply_filters(query, filters)
        query = self._apply_search(query, search)

        return query.order_by(self.model.id).offset(skip).limit(limit).all()

    def get_brief(
        self,
        *columns: Any,
        order_by: Any = None,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> list[Any]:
        """
        Retrieve a paginated page of specific columns (no relationship loading).

        Args:
            *columns: Model columns to select.
            order_by: Optional column(s) to order by.
            skip: Records to skip.
            limit: Max records to return.
            filters: Exact-match filters against ``self.model``.
            search: Substring match against ``self._search_fields``.

        Returns:
            A list of ``Row`` tuples in column order.
        """

        query = self.db.query(*columns)
        query = self._apply_filters(query, filters)
        query = self._apply_search(query, search)

        if order_by is not None:
            query = query.order_by(order_by)

        return query.offset(skip).limit(limit).all()

    def count_all(self) -> int:
        """Count all records in the table."""

        return self.db.query(self.model).count()

    def count(self, *, filters: dict[str, Any] | None = None, search: str | None = None) -> int:
        """Count records matching ``filters``/``search`` (same conditions as :meth:`get_all`)."""

        query = self.db.query(self.model)
        query = self._apply_filters(query, filters)
        query = self._apply_search(query, search)

        return query.count()

    def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if any ``self._unique_fields`` value already exists."""

        if not self._unique_fields:
            return

        for field in self._unique_fields:
            if field in data and data[field] is not None:
                value = data[field]
                query = self.db.query(self.model).filter(getattr(self.model, field) == value)

                if exclude_id is not None:
                    query = query.filter(self.model.id != exclude_id)

                if query.first() is not None:
                    raise RecordAlreadyExistsError(model_name=self.model.__name__, field=field, value=value)

    def create(self, obj_data: dict[str, Any], *, commit: bool = True) -> ModelType:
        """
        Create a record from ``obj_data`` and return it.

        ``commit=False`` flushes instead of committing, leaving the
        transaction open for the caller (e.g. inside ``session.begin_nested()``).
        """

        self._check_uniqueness(obj_data)

        db_obj = self.model(**obj_data)
        self.db.add(db_obj)

        if commit:
            try:
                self.db.commit()
                self.db.refresh(db_obj)
            except SQLAlchemyError:
                self.db.rollback()
                raise
        else:
            self.db.flush()

        return db_obj

    def update(self, db_obj: ModelType, update_data: dict[str, Any], *, refresh: bool = False) -> ModelType:
        """Apply ``update_data`` onto ``db_obj`` and commit. Unknown keys are ignored."""

        self._check_uniqueness(update_data, exclude_id=db_obj.id)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        try:
            self.db.commit()
            if refresh:
                self.db.refresh(db_obj)
        except SQLAlchemyError:
            self.db.rollback()
            raise

        return db_obj

    def delete(self, db_obj: ModelType) -> bool:
        """Delete ``db_obj``, returning ``True`` on success."""

        try:
            self.db.delete(db_obj)
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

        return True

    def refresh(self, db_obj: ModelType) -> ModelType:
        """Reload ``db_obj`` from the database and return it."""

        self.db.refresh(db_obj)
        return db_obj

    def exists_by_id(self, model_id: int) -> bool:
        """Return whether a record with ``model_id`` exists, without loading it."""

        return self.db.query(self.model).filter(self.model.id == model_id).first() is not None
