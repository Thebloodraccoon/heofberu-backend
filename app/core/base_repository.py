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

    Eager loading (avoiding N+1):
        If the model has relationships that the feature's response schema
        always includes (e.g. ``ClassResponse`` always serializes
        ``primary_abilities``, ``saving_throws``, etc.), pass
        ``default_load_options`` to ``__init__`` instead of overriding
        :meth:`get_by_id`/:meth:`get_all` just to bolt on ``.options(...)``.
        Each item is a loader option from ``sqlalchemy.orm``
        (``selectinload(...)``, ``joinedload(...)``, etc.) — typed as
        ``list[Any]`` here rather than SQLAlchemy's internal loader-option
        type, since that type is a private implementation detail not meant
        for external annotation::

            class ClassRepository(BaseRepository[Class]):
                def __init__(self, db: Session):
                    super().__init__(
                        Class,
                        db,
                        default_load_options=[
                            selectinload(Class.primary_abilities),
                            selectinload(Class.saving_throws),
                            selectinload(Class.available_skills),
                            selectinload(Class.spell_slot_progression),
                        ],
                    )

        ``get_by_id`` and ``get_all`` apply these automatically on every
        call — there's no per-call toggle. This is deliberate: a
        relationship that's *always* in the response schema should
        *always* be eager-loaded, on every codepath that returns the full
        model, not opted into ad hoc at each call site (which is exactly
        how the N+1s crept in originally — a repository method got added
        without anyone remembering to add ``.options(...)`` to it). If a
        feature genuinely needs a cheaper query that skips relationships
        (e.g. a bulk existence check), add a distinct method for it rather
        than a flag on these.

        Prefer ``selectinload`` over ``joinedload`` for collections — it
        issues one extra ``SELECT ... WHERE id IN (...)`` per relationship
        instead of a row-multiplying ``JOIN``, so N+1 becomes a small,
        fixed number of queries regardless of page size. ``joinedload``
        is appropriate for a many-to-one/one-to-one relationship or when
        rows are always fetched one at a time.

        A repository with no relationships to eager-load (or whose
        response schema doesn't include any) can simply omit
        ``default_load_options`` — ``get_by_id``/``get_all`` behave exactly
        as before.

    Free-text search (as opposed to ``filters``'s exact match):
        :meth:`get_all` and :meth:`get_brief` both accept an optional
        ``search`` string, applied via :meth:`_apply_search` as a
        case-insensitive substring match (``ILIKE``) across one or more
        text columns, OR'd together — unlike ``filters``, which is
        exact-match and AND's each key.

        By default (``search_fields`` omitted), the columns searched are
        auto-detected: every ``String``/``Text`` column on ``model``, found
        via SQLAlchemy's mapper inspection. This is a reasonable default
        for a small model but is not always what's wanted — e.g. searching
        a free-text ``description`` column alongside ``name`` may return
        surprising matches, and inspecting every column on every call has a
        (small, but nonzero) cost.

        Pass ``search_fields`` to pin the search to specific columns
        instead, the same way ``default_load_options`` pins eager-loading::

            class RaceRepository(BaseRepository[Race]):
                def __init__(self, db: Session):
                    super().__init__(Race, db, search_fields=["name"])

        Passing ``search_fields=[]`` explicitly (as opposed to leaving it
        ``None``) disables search entirely for that repository — ``search``
        is then silently ignored rather than falling back to
        auto-detection.

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
        """
        Auto-detect ``String``/``Text`` column names on ``self.model``.

        Used as the fallback for ``search_fields`` when a repository
        doesn't pin an explicit list — see the class docstring's
        "Free-text search" section. Uses ``sqlalchemy.inspect`` rather than
        ``self.model.__table__.columns`` so this also works with columns
        declared via ``Mapped[...]``/``mapped_column(...)`` annotations,
        not just the legacy ``Column(...)`` style.
        """

        mapper = inspect(self.model)
        return [column.key for column in mapper.columns if isinstance(column.type, String | Text)]

    def _apply_filters(self, query: Any, filters: dict[str, Any] | None) -> Any:
        """
        Apply exact-match filters to ``query`` for the keys in ``filters``.

        Shared by :meth:`get_all`, :meth:`get_brief`, and
        :meth:`filter_by_fields` so "filter on some optional fields" has
        one implementation instead of three. Only keys that correspond to
        an actual attribute on ``self.model`` and whose value is not
        ``None`` become a filter condition — a ``None`` value means "don't
        restrict on this field" (the same convention ``get_filtered``-style
        feature methods already use), not "field IS NULL"; this method
        isn't suitable for querying nulls.
        """

        if not filters:
            return query

        for field, value in filters.items():
            if hasattr(self.model, field) and value is not None:
                query = query.filter(getattr(self.model, field) == value)

        return query

    def _apply_search(self, query: Any, search: str | None) -> Any:
        """
        Apply a case-insensitive substring ``search`` across ``self._search_fields``.

        Shared by :meth:`get_all` and :meth:`get_brief`, the same way
        :meth:`_apply_filters` is — see the class docstring's "Free-text
        search" section for how ``self._search_fields`` gets set
        (auto-detected ``String``/``Text`` columns, or the explicit
        ``search_fields`` passed to ``__init__``).

        Each field becomes an ``ILIKE %search%`` condition; a record
        matches if *any* field matches (``OR``), unlike ``_apply_filters``,
        whose conditions are ANDed. A single ``search_fields`` entry
        collapses to a plain ``WHERE field ILIKE ...`` (no redundant
        ``OR`` wrapper); a record matching on more than one field still
        appears once, since the ``OR`` is part of one SQL ``WHERE``
        clause, not a union of separate queries. A blank/``None`` ``search``
        or an empty ``self._search_fields`` leaves ``query`` untouched.
        """

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
        """
        Retrieve a single record by its primary key ID, or ``None`` if missing.

        Applies ``default_load_options`` (if the repository was constructed
        with any) so a single-record fetch doesn't N+1 on access to the
        same relationships the paginated ``get_all`` eager-loads.
        """

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
        Retrieve multiple records with offset-based pagination.

        This is always paginated — feature repositories should not
        override it to return a full list. Use :meth:`get_all_brief` for
        a quick, unpaginated listing of specific columns instead.

        Applies ``default_load_options`` (if the repository was constructed
        with any) — see the "Eager loading" section on the class docstring.

        Orders by ``id`` by default. This isn't about presentation — it's
        what makes ``skip``/``limit`` pagination stable: without *some*
        ``ORDER BY``, the database is free to return rows in a different
        order on each call (plan changes, concurrent writes, vacuum,
        etc.), which shows up as duplicated or skipped rows across pages.
        A feature repository that needs a different sort (by name, by
        creation date, ...) should override :meth:`get_all` and supply its
        own ``order_by`` — id-order is only the fallback for features that
        don't care.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            filters: Optional exact-match filters, e.g.
                ``{"source_type": FeatureSourceType.CLASS, "class_id": 3}``.
                Only keys naming an actual model attribute, with a value
                that isn't ``None``, are applied — omit a key (or pass
                ``None`` for it) to mean "don't restrict on this field".
                Lets a feature's ``GET /{feature}/?class_id=3``-style
                filtered listing reuse this method instead of writing its
                own ``get_filtered`` (see :meth:`_apply_filters`). A
                feature needing filters combined with its own ``order_by``
                (e.g. ``FeatureRepository.get_filtered`` ordering by name)
                should still override :meth:`get_all` rather than relying
                on the id-order fallback.
            search: Optional case-insensitive substring match, OR'd across
                ``self._search_fields`` — see the class docstring's
                "Free-text search" section for how those fields are chosen.
                Combines with ``filters`` (AND'd together): e.g.
                ``filters={"size": "MEDIUM"}, search="elf"`` returns medium
                races with "elf" somewhere in a searched field.

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
        Retrieve a paginated page of lightweight rows for the given columns.

        This is the paginated counterpart to :meth:`get_all_brief`: it
        selects only the given columns (no relationship loading, no full
        model instantiation) but still applies ``skip``/``limit``, making
        it the standard building block behind every feature's
        ``GET /{feature}/brief`` listing endpoint.

        Args:
            *columns: The model columns to select, e.g.
                ``repository.get_brief_paginated(Class.id, Class.name)``.
                At least one column must be given.
            order_by: Optional column (or list of columns) to order by.
                Pass the model's natural sort key, e.g. ``Class.name``.
                If omitted, row order is left to the database.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            filters: Optional exact-match filters against ``self.model``
                (not against ``columns``) — see :meth:`get_all` for the
                exact semantics and :meth:`_apply_filters` for the
                implementation. Filtering still works even though the
                query only selects specific columns, since the filter
                conditions reference the model's attributes directly, not
                the selected columns.
            search: Optional case-insensitive substring match against
                ``self._search_fields`` on ``self.model`` — same semantics
                as on :meth:`get_all` (see :meth:`_apply_search`). Also
                works against unselected columns, same reasoning as
                ``filters`` above.

        Returns:
            A list of ``Row`` tuples, one per record, in column order.

        """

        query = self.db.query(*columns)
        query = self._apply_filters(query, filters)
        query = self._apply_search(query, search)

        if order_by is not None:
            query = query.order_by(order_by)

        return query.offset(skip).limit(limit).all()

    def count_all(self) -> int:
        """Count the total number of records in the table, unconditionally."""

        return self.db.query(self.model).count()

    def count(self, *, filters: dict[str, Any] | None = None, search: str | None = None) -> int:
        """
        Count records matching ``filters``/``search``, using the same
        conditions as :meth:`get_all`/:meth:`get_brief`.

        This is the counterpart needed for a ``{items, total, page, size}``
        listing response: the item count for the *current page* is
        ``len(items)``, but ``total`` (the count across all pages) must be
        computed by re-running the same ``filters``/``search`` conditions
        without ``offset``/``limit``. Kept as a separate method rather than
        folded into ``get_all`` since a ``COUNT(*)`` query and a row-fetch
        query are different queries — combining them would mean either two
        round-trips disguised as one call, or a less efficient combined
        query (e.g. a window function) that isn't needed for the common
        case.

        No ``default_load_options`` here — a count doesn't touch
        relationships, so eager-loading is irrelevant (and would be wasted
        work) for this query.
        """

        query = self.db.query(self.model)
        query = self._apply_filters(query, filters)
        query = self._apply_search(query, search)

        return query.count()

    def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """
        Checks the uniqueness of the fields specified in self._unique_fields.
        If the value already exists, throws a generic error.
        """
        
        if not self._unique_fields:
            return

        for field in self._unique_fields:
            if field in data and data[field] is not None:
                value = data[field]
                query = self.db.query(self.model).filter(getattr(self.model, field) == value)

                if exclude_id is not None:
                    query = query.filter(self.model.id != exclude_id)

                if query.first() is not None:
                    raise RecordAlreadyExistsError(
                        model_name=self.model.__name__,
                        field=field,
                        value=value
                    )

    def create(self, obj_data: dict[str, Any], *, commit: bool = True) -> ModelType:
        """
        Create a new record from ``obj_data`` and return it.

        ``obj_data`` is passed as keyword arguments to the model's
        constructor, so its keys must match the model's column/attribute
        names (this is how ``BaseService.create`` feeds it a schema's
        ``model_dump()`` output).

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a record plus rows in related association tables,
        all-or-nothing) defer the commit and flush instead. When
        ``commit=False``, the returned instance has its autogenerated
        fields (id, defaults, etc.) populated via ``flush()``, but the
        transaction is left open for the caller to commit or roll back.

        IMPORTANT: never wrap a call to this method (or ``update``/
        ``delete``, which also default to committing) inside
        ``session.begin_nested()`` without passing ``commit=False`` — an
        inner ``session.commit()`` commits the *entire* outer transaction,
        not just the nested SAVEPOINT, which leaves the ``begin_nested()``
        context manager holding a reference to an already-closed
        transaction and raises ``Can't operate on closed transaction``
        on exit.
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
        """
        Apply ``update_data`` onto an existing record and return it, refreshed.

        Only keys that already exist as attributes on ``db_obj`` are set
        (via ``hasattr``); unknown keys are silently ignored rather than
        raising, so callers should validate field names upstream (e.g.
        through a Pydantic update schema) if stricter behavior is needed.
        """

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
        """Delete ``db_obj`` from the database, returning ``True`` on success."""

        try:
            self.db.delete(db_obj)
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

        return True

    def refresh(self, db_obj: ModelType) -> ModelType:
        """
        Reload ``db_obj``'s attributes from the database and return it.

        Exists mainly for the ``BaseService._atomic()`` call site: after a
        multi-write transaction committed via ``_atomic()``, the caller
        needs to refresh the just-created instance to pick up
        autogenerated fields (id, defaults, etc.), but shouldn't have to
        reach into ``self.repository.db.refresh(...)`` to do it — that
        exposes the raw ``Session`` to the service layer for a single call.
        ``create``/``update`` already call ``self.db.refresh`` internally
        when appropriate; this just makes the same operation available as
        a first-class repository method for callers that manage their own
        transaction (e.g. via ``_atomic()``).
        """

        self.db.refresh(db_obj)
        return db_obj

    def exists_by_id(self, model_id: int) -> bool:
        """Return whether a record with ``model_id`` exists, without loading it."""

        return self.db.query(self.model).filter(self.model.id == model_id).first() is not None
