"""
Generic service layer: fetch -> validate -> persist -> serialize orchestration.

Provides :class:`BaseService` (a model-generic CRUD orchestrator sitting on
top of :class:`BaseRepository`) and the schema type variables services bind to.

Async stack: every orchestration method is ``async`` (repository calls are
awaited); ``_atomic`` / ``_unit_of_work`` wrap multistep writes in one
transaction (see ``app.core.base.transaction``).
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Generic

from pydantic import BaseModel
from sqlalchemy import inspect
from typing_extensions import TypeVar

from app.core.base.repository import BaseRepository, ModelType
from app.core.base.transaction import UnitOfWork, after_commit, atomic, unit_of_work
from app.core.cache.invalidation import invalidate
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.core.pagination import Page, paginate

CreateSchema = TypeVar("CreateSchema", bound=BaseModel)
UpdateSchema = TypeVar("UpdateSchema", bound=BaseModel)
ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)
GetAllSchema = TypeVar("GetAllSchema", bound=BaseModel, default=BaseModel)
BeforeUpdateHook = Callable[[ModelType, dict], None]

ResolvedItem = TypeVar("ResolvedItem")


class BaseService(Generic[ModelType, CreateSchema, UpdateSchema, ResponseSchema, GetAllSchema]):
    """
    Generic "fetch → validate → persist → serialize" CRUD orchestration on
    top of a :class:`BaseRepository`.

    Type parameters:
        ModelType: SQLAlchemy model handled by the repository.
        CreateSchema: Schema accepted by :meth:`create`.
        UpdateSchema: Schema accepted by :meth:`update` (partial update).
        ResponseSchema: Schema used to serialize results.
        GetAllSchema: Optional lightweight schema for :meth:`get_all`
            (listings of reference catalogs). ``None`` means full records
            are serialized to ``ResponseSchema`` instead.

    Caching: services that should be cached transparently declare
    ``cache_namespaces`` and decorate read methods with
    ``app.core.cache.use_cache``. Every write here
    (:meth:`create`/:meth:`update`/:meth:`delete`) purges those namespaces
    automatically via :meth:`_invalidate_cache`; subclasses with compound
    write methods must call ``self._invalidate_cache()`` themselves. Inside
    :meth:`_atomic` / :meth:`_unit_of_work` the purge is deferred until the
    transaction has committed.

    Example::

        class SpellService(
            BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellGetAllResponse]
        ):
            cache_namespaces = ("spells",)

            def __init__(self, db: AsyncSession):
                super().__init__(
                    repository=SpellRepository(db),
                    response_schema=SpellResponse,
                    get_all_schema=SpellGetAllResponse,
                )
    """

    cache_namespaces: tuple[str, ...] = ()

    # NAME of the model column ``get_all`` listings are ordered by (e.g. ``"name"``);
    # ``None`` keeps ``model.id`` order. A string so no mapped attribute lives on the class.
    get_all_order_by: str | None = None

    def __init__(
        self,
        repository: BaseRepository[ModelType],
        response_schema: type[ResponseSchema],
        get_all_schema: type[GetAllSchema] | None = None,
    ):
        self.repository = repository
        self.response_schema = response_schema
        self.get_all_schema = get_all_schema

    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[ResponseSchema]:
        """
        Return a page of records.

        When ``get_all_schema`` is set (reference catalogs), this is a
        lightweight listing: rows are fetched through the column-select path
        (``BaseRepository.get_brief``) using the schema's field names as
        columns, so heavy full records with eager-loaded relationships are
        never materialized. If the schema contains fields that aren't plain
        mapped columns (relationships, e.g. a spell's ``available_classes``,
        or Python ``@property`` attributes like a feature's ``effects_summary``), the
        column-select path can't resolve them, so the listing falls back to
        the eager-loaded ``repository.get_all`` (via the repository's
        ``default_load_options``) instead. ``total`` always comes from
        ``repository.count``.

        When ``get_all_schema`` is ``None`` (e.g. users/characters), full
        records are fetched and serialized to ``ResponseSchema``.

        Args:
            page: 1-indexed page number.
            size: Records per page.
            filters: Exact-match filters, passed to ``repository.get_all``.
            search: Substring match, passed to ``repository.get_all``.
        """

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)

        if self.get_all_schema is None:
            items = await self.repository.get_all(skip=skip, limit=limit, filters=filters, search=search)
            return Page(
                items=[self.response_schema.model_validate(item) for item in items],
                total=total,
                page=page,
                size=size,
            )

        model = self.repository.model
        mapper = inspect(model)
        non_column_fields = [name for name in self.get_all_schema.model_fields if name not in mapper.columns]

        order_by = getattr(model, self.get_all_order_by) if self.get_all_order_by else None

        if not non_column_fields:
            columns = [getattr(model, field_name) for field_name in self.get_all_schema.model_fields]
            rows = await self.repository.get_brief(
                *columns,
                order_by=order_by,
                skip=skip,
                limit=limit,
                filters=filters,
                search=search,
            )
            items = [self.get_all_schema.model_validate(row, from_attributes=True) for row in rows]
        else:
            records = await self.repository.get_all(
                skip=skip,
                limit=limit,
                filters=filters,
                search=search,
                order_by=order_by,
            )
            items = [self.get_all_schema.model_validate(record) for record in records]

        return Page(items=items, total=total, page=page, size=size)

    async def get_by_id(self, item_id: int) -> ResponseSchema:
        """Return a single record by ID, or raise ``RecordNotFoundError``."""

        item = await self._get_or_404(item_id)
        return self.response_schema.model_validate(item)

    async def create(self, create_data: CreateSchema) -> ResponseSchema:
        """Persist a new record and return it serialized. No business-rule validation is done here."""

        item = await self.repository.create(create_data.model_dump())
        await self._invalidate_cache()
        return self.response_schema.model_validate(item)

    async def update(
        self,
        item_id: int,
        update_data: UpdateSchema,
        *,
        before_update: BeforeUpdateHook | None = None,
    ) -> ResponseSchema:
        """
        Partially update a record (``exclude_unset=True``) and return it serialized.

        Args:
            item_id: ID of the record to update.
            update_data: Schema with the fields to apply.
            before_update: Optional ``before_update(item, fields)`` hook run
                before persisting; may mutate ``fields`` or raise to abort.
        """

        item = await self._get_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)

        if before_update:
            before_update(item, fields)

        updated_item = await self.repository.update(item, fields)
        await self._invalidate_cache()
        return self.response_schema.model_validate(updated_item)

    async def delete(self, item_id: int) -> bool:
        """
        Delete a record by ID, returning ``True`` on success.

        If the repository was constructed with ``check_in_use_on_delete=True``,
        ``self.repository.delete`` itself raises ``RecordInUseError`` when
        the record is still referenced elsewhere -- no extra handling
        needed here; see ``BaseRepository.delete``/``is_in_use``.
        """
        item = await self._get_or_404(item_id)
        result = await self.repository.delete(item)
        await self._invalidate_cache()
        return result

    async def _invalidate_cache(self) -> None:
        """
        Purge all cached entries for this service's namespaces after a write.

        Inside :meth:`_atomic` / :meth:`_unit_of_work` the purge runs only
        after the transaction commits (and is dropped on rollback); outside
        it runs immediately, the repository having already committed.
        """

        if self.cache_namespaces:
            await after_commit(self.repository.db, self._purge_namespaces)

    async def _purge_namespaces(self) -> None:
        for namespace in self.cache_namespaces:
            await invalidate(namespace)

    async def _get_or_404(self, item_id: int) -> ModelType:
        """Fetch the raw model instance or raise ``RecordNotFoundError``."""

        item = await self.repository.get_by_id(item_id)
        if not item:
            raise RecordNotFoundError(model_name=self.repository.model.__name__, model_id=str(item_id))

        return item

    async def _exists_or_404(self, item_id: int) -> None:
        """
        Raise ``RecordNotFoundError`` unless ``item_id`` exists.

        A cheap presence-only check (``repository.exists_by_id``) for callers
        that only need to 404-guard a parent id and don't use the fetched
        record — use ``_get_or_404`` instead when the record itself is needed.
        """

        if not await self.repository.exists_by_id(item_id):
            raise RecordNotFoundError(model_name=self.repository.model.__name__, model_id=str(item_id))

    async def _get_response(self, item_id: int) -> ResponseSchema:
        """Fetch a record by id, serialize it to ``response_schema``, or raise ``RecordNotFoundError``."""

        return self.response_schema.model_validate(await self._get_or_404(item_id))

    @staticmethod
    async def resolve_ids(
        lookup_fn: Callable[[list[int]], Awaitable[list[ResolvedItem]]], ids: list[int], model_name: str
    ) -> list[ResolvedItem]:
        """Resolve ``ids`` via ``lookup_fn``, raising ``RecordIdsInvalidError`` if any don't resolve."""

        if not ids:
            return []

        founds = await lookup_fn(ids)
        found_ids = {found.id for found in founds}
        missing_ids = [item_id for item_id in ids if item_id not in found_ids]

        if missing_ids:
            raise RecordIdsInvalidError(model_name=model_name, ids=missing_ids)

        return founds

    @asynccontextmanager
    async def _atomic(self) -> AsyncGenerator[None, None]:
        """
        Wrap a multistep write in a single all-or-nothing transaction.

        Every repository write inside the ``async with`` block MUST pass
        ``commit=False``. Commits once on success and then runs the deferred
        cache purges; rolls back and re-raises on any exception. For a single
        repository call, ``commit=True`` (the default) is enough.
        """

        async with atomic(self.repository.db):
            yield

    @asynccontextmanager
    async def _unit_of_work(self) -> AsyncGenerator[UnitOfWork, None]:
        """:meth:`_atomic` that yields a :class:`UnitOfWork` for scheduling post-commit work."""

        async with unit_of_work(self.repository.db) as uow:
            yield uow
