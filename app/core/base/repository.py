"""
Generic repository layer: common CRUD operations for SQLAlchemy models.

Provides :class:`BaseRepository` (a reusable, model-generic CRUD base with
filtering, search, pagination, uniqueness checks and delete-in-use guards)
plus the model protocol and type aliases it relies on.

Async stack: all public methods are ``async`` and run against an
``AsyncSession`` using 2.0-style ``select()`` statements.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy import String, Text, delete, func, inspect, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordAlreadyExistsError, RecordInUseError


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
        db: Active async session.
        default_load_options: Loader options (``selectinload``,
            ``joinedload``, ...) applied automatically on
            :meth:`get_by_id`/:meth:`get_all`, for relationships the
            response schema always includes.
        search_fields: Columns used by :meth:`_apply_search`. Defaults to
            auto-detected ``String``/``Text`` columns; pass ``[]`` to
            disable search.
        unique_fields: Columns checked by :meth:`_check_uniqueness` on
            create/update.
        check_in_use_on_delete: If ``True``, :meth:`delete` calls
            :meth:`is_in_use` first and raises ``RecordInUseError``
            instead of deleting. Subclasses opting in MUST override
            :meth:`is_in_use`; the base implementation raises
            ``NotImplementedError``.

    Example::

        class SpellRepository(BaseRepository[Spell]):
            def __init__(self, db: AsyncSession):
                super().__init__(Spell, db)

        class FeatRepository(BaseRepository[Feat]):
            def __init__(self, db: AsyncSession):
                super().__init__(Feat, db, unique_fields=["name"], check_in_use_on_delete=True)

            async def is_in_use(self, model_id: int) -> bool:
                return await self.db.scalar(
                    select(CharacterFeat.feat_id).where(CharacterFeat.feat_id == model_id)
                ) is not None
    """

    def __init__(
        self,
        model: type[ModelType],
        db: AsyncSession,
        default_load_options: list[Any] | None = None,
        search_fields: list[str] | None = None,
        unique_fields: list[str] | None = None,
        check_in_use_on_delete: bool = False,
    ):
        self.model = model
        self.db = db
        self._default_load_options = default_load_options or []
        self._search_fields = search_fields if search_fields is not None else self._detect_text_fields()
        self._unique_fields = unique_fields or []
        self._check_in_use_on_delete = check_in_use_on_delete

    def _detect_text_fields(self) -> list[str]:
        """Auto-detect ``String``/``Text`` column names on ``self.model``."""

        mapper = inspect(self.model)
        return [column.key for column in mapper.columns if isinstance(column.type, String | Text)]

    def _apply_filters(self, stmt: Any, filters: dict[str, Any] | None) -> Any:
        """Apply exact-match, AND'd filters for known, non-``None`` keys in ``filters``."""

        if not filters:
            return stmt

        for field, value in filters.items():
            if hasattr(self.model, field) and value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)

        return stmt

    def _apply_search(self, stmt: Any, search: str | None) -> Any:
        """Apply a case-insensitive ``ILIKE`` substring match, OR'd across ``self._search_fields``."""

        if not search or not self._search_fields:
            return stmt

        conditions = [
            getattr(self.model, field).ilike(f"%{search}%")
            for field in self._search_fields
            if hasattr(self.model, field)
        ]

        if not conditions:
            return stmt

        return stmt.where(or_(*conditions))

    async def get_by_id(self, model_id: int) -> ModelType | None:
        """Retrieve a single record by ID, or ``None`` if missing. Applies ``default_load_options``."""

        stmt = select(self.model)
        if self._default_load_options:
            stmt = stmt.options(*self._default_load_options)

        stmt = stmt.where(self.model.id == model_id)

        # Repopulate an existing identity-map instance instead of returning its
        # stale state: mutation flows (child-row replacement, ``db.expire`` after
        # feature edits) leave in-memory collections out of sync with the DB.
        return await self.db.scalar(stmt.execution_options(populate_existing=True))

    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        order_by: Any = None,
    ) -> list[ModelType]:
        """
        Retrieve records with offset-based pagination, ordered by ``id``
        (or ``order_by`` if given).

        Applies ``default_load_options``, ``filters`` (exact-match, AND'd),
        and ``search`` (substring, OR'd across search fields).

        Args:
            skip: Records to skip.
            limit: Max records to return. ``None`` disables the limit.
            filters: Exact-match filters against ``self.model``.
            search: Substring match against ``self._search_fields``.
            order_by: Optional column(s) to order by; defaults to ``self.model.id``.
        """

        stmt = select(self.model)
        if self._default_load_options:
            stmt = stmt.options(*self._default_load_options)

        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_search(stmt, search)

        stmt = stmt.order_by(order_by if order_by is not None else self.model.id)

        if skip:
            stmt = stmt.offset(skip)

        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_brief(
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

        stmt = select(*columns)
        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_search(stmt, search)

        if order_by is not None:
            stmt = stmt.order_by(order_by)

        result = await self.db.execute(stmt.offset(skip).limit(limit))
        return list(result.all())

    async def count_all(self) -> int:
        """Count all records in the table."""

        stmt = select(func.count()).select_from(self.model)
        return (await self.db.scalar(stmt)) or 0

    async def count(self, *, filters: dict[str, Any] | None = None, search: str | None = None) -> int:
        """Count records matching ``filters``/``search`` (same conditions as :meth:`get_all`)."""

        stmt = select(func.count()).select_from(self.model)
        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_search(stmt, search)

        return (await self.db.scalar(stmt)) or 0

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if any ``self._unique_fields`` value already exists."""

        if not self._unique_fields:
            return

        for field in self._unique_fields:
            if field in data and data[field] is not None:
                value = data[field]
                stmt = select(self.model.id).where(getattr(self.model, field) == value)

                if exclude_id is not None:
                    stmt = stmt.where(self.model.id != exclude_id)

                if await self.db.scalar(stmt) is not None:
                    raise RecordAlreadyExistsError(model_name=self.model.__name__, field=field, value=value)

    @asynccontextmanager
    async def _commit_or_rollback(self) -> AsyncGenerator[None, None]:
        """Commit on success, rollback and re-raise on SQLAlchemyError."""

        try:
            yield
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    async def create(self, obj_data: dict[str, Any], *, commit: bool = True) -> ModelType:
        """
        Create a record from ``obj_data`` and return it.

        ``commit=False`` flushes instead of committing, leaving the
        transaction open for the caller (e.g. inside ``begin_nested()``).
        """

        await self._check_uniqueness(obj_data)

        db_obj = self.model(**obj_data)
        self.db.add(db_obj)

        if commit:
            async with self._commit_or_rollback():
                pass
            await self.db.refresh(db_obj)
        else:
            await self.db.flush()

        return db_obj

    async def update(self, db_obj: ModelType, update_data: dict[str, Any], *, refresh: bool = False) -> ModelType:
        """Apply ``update_data`` onto ``db_obj`` and commit. Unknown keys are ignored."""

        await self._check_uniqueness(update_data, exclude_id=db_obj.id)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        async with self._commit_or_rollback():
            pass
        if refresh:
            await self.db.refresh(db_obj)

        return db_obj

    async def is_in_use(self, model_id: int) -> bool:
        """
        Return whether ``model_id`` is still referenced elsewhere and
        therefore cannot be deleted.

        Only called by :meth:`delete` when ``check_in_use_on_delete=True``
        was passed in ``__init__``. Base implementation raises
        ``NotImplementedError`` -- subclasses opting in via that flag MUST
        override this with their own FK check (see class docstring).
        """

        raise NotImplementedError(
            f"{type(self).__name__} was constructed with check_in_use_on_delete=True but does not override is_in_use()."
        )

    async def delete(self, db_obj: ModelType) -> bool:
        """
        Delete ``db_obj``, returning ``True`` on success.

        If ``check_in_use_on_delete`` was set in ``__init__``, calls
        :meth:`is_in_use` first and raises ``RecordInUseError`` instead of
        deleting -- plus a ``SQLAlchemyError`` safety net around the actual
        delete, in case of a race between the check and the delete
        (relevant when the guarded FK is ``ON DELETE RESTRICT``).
        """

        if self._check_in_use_on_delete and await self.is_in_use(db_obj.id):
            raise RecordInUseError(model_name=self.model.__name__, model_id=db_obj.id)

        try:
            async with self._commit_or_rollback():
                await self.db.delete(db_obj)
        except SQLAlchemyError:
            raise RecordInUseError(model_name=self.model.__name__, model_id=db_obj.id)

        return True

    async def refresh(self, db_obj: ModelType) -> ModelType:
        """Reload ``db_obj`` from the database and return it."""

        await self.db.refresh(db_obj)
        return db_obj

    async def exists_by_id(self, model_id: int) -> bool:
        """
        Return whether a record with ``model_id`` exists, as a bool.

        Only the primary key is selected, so the check stays a lightweight
        presence query.
        """

        stmt = select(self.model.id).where(self.model.id == model_id).limit(1)
        return await self.db.scalar(stmt) is not None

    async def get_many_by_ids(
        self,
        model: Any,
        ids: list[int],
        *,
        load_options: list[Any] | None = None,
    ) -> list[Any]:
        """
        Fetch the ``model`` records whose ids are in ``ids`` (order not guaranteed).

        Generic ``SELECT ... WHERE id IN (...)`` used by the reference
        lookups (``get_skills_by_ids``, ``get_classes_by_ids``,
        ``get_races_by_ids``) so the id-IN pattern is defined once.

        Args:
            model: SQLAlchemy model to query (need not be ``self.model``).
            ids: Ids to fetch.
            load_options: Optional loader options applied to the statement.
        """

        if not ids:
            return []

        stmt = select(model).where(model.id.in_(ids))
        if load_options:
            stmt = stmt.options(*load_options)

        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def replace_association(
        self,
        association: Any,
        parent: Any,
        parent_fk: str,
        child_fk: str,
        child_ids: list[int],
        *,
        commit: bool = True,
    ) -> None:
        """
        Replace a many-to-many association with ``child_ids`` in one batch.

        Deletes the parent's existing rows, inserts one row per new child
        id, then commits (or flushes when ``commit=False``). Written through
        the association table instead of assigning the ORM relationship:
        assigning an unloaded many-to-many collection would trigger a lazy
        load, which is not supported on the async stack.

        Args:
            association: The ``Table`` (or mapped class) linking parent and child.
            parent: The owning model instance.
            parent_fk: Column name on ``association`` referencing ``parent``.
            child_fk: Column name on ``association`` referencing the child.
            child_ids: New child ids (``[]`` clears the association).
            commit: ``False`` flushes instead, leaving the transaction open.
        """

        parent_column = getattr(association, "c", None)
        if parent_column is not None:
            parent_column = parent_column[parent_fk]
        else:
            parent_column = getattr(association, parent_fk)

        await self.db.execute(delete(association).where(parent_column == parent.id))

        if child_ids:
            await self.db.execute(
                association.insert(),
                [{parent_fk: parent.id, child_fk: child_id} for child_id in child_ids],
            )

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def replace_child_rows(
        self,
        child_model: Any,
        parent: Any,
        fk_name: str,
        rows: list[dict[str, Any]],
        *,
        extra_filters: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        """
        Replace the ``child_model`` rows owned by ``parent`` in one batch.

        Deletes the parent's existing rows (optionally restricted by
        ``extra_filters``, e.g. ``{"class_level": 3}``), then adds a fresh
        ``child_model`` row per entry in ``rows``. Commits (or flushes when
        ``commit=False``).

        Args:
            child_model: ORM model of the child rows.
            parent: The owning model instance.
            fk_name: Column name on ``child_model`` referencing ``parent``.
            rows: Child payloads, each without the FK column (it is injected).
            extra_filters: Extra exact-match filters on the delete
                (e.g. scoping to a single ``class_level``).
            commit: ``False`` flushes instead, leaving the transaction open.
        """

        stmt = delete(child_model).where(getattr(child_model, fk_name) == parent.id)
        for field, value in (extra_filters or {}).items():
            stmt = stmt.where(getattr(child_model, field) == value)
        await self.db.execute(stmt)

        for row in rows:
            self.db.add(child_model(**{fk_name: parent.id, **row}))

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def exists_referencing(self, referencing_model: Any, fk_name: str, value: Any) -> bool:
        """
        Return whether any ``referencing_model`` row has ``fk_name`` == ``value``.

        Lightweight presence check (``LIMIT 1``) used by the in-use delete
        guards (``is_in_use``) so the FK-existence pattern is defined once.
        """

        stmt = select(referencing_model).where(getattr(referencing_model, fk_name) == value).limit(1)
        return await self.db.scalar(stmt) is not None
