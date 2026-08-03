from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Generic

from fastapi import HTTPException
from pydantic import BaseModel
from starlette import status
from typing_extensions import TypeVar

from app.core.base_repository import BaseRepository, ModelType
from app.core.exceptions import RecordAlreadyExistsError, RecordNotFoundError

CreateSchema = TypeVar("CreateSchema", bound=BaseModel)
UpdateSchema = TypeVar("UpdateSchema", bound=BaseModel)
ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)
BriefSchema = TypeVar("BriefSchema", bound=BaseModel, default=BaseModel)

NotFoundExceptionFactory = Callable[[int], Exception]
BeforeUpdateHook = Callable[[ModelType, dict], None]

ItemSchema = TypeVar("ItemSchema", bound=BaseModel)


class Page(BaseModel, Generic[ItemSchema]):
    """
    Generic ``{items, total, page, size}`` envelope for a paginated listing.

    Replaces returning a bare ``list[ResponseSchema]`` from
    :meth:`BaseService.get_all`/:meth:`BaseService.list_brief`: a bare list
    tells the caller nothing about how many records exist beyond the
    current page, so a client can't render "page 3 of 12" or know whether
    to show a "next page" control without a second, separate request.

    ``page``/``size`` here echo back the *request's* pagination (1-indexed
    page number and page size) rather than the ``skip``/``limit`` the
    repository layer uses internally — ``skip``/``limit`` is
    offset/count, which is the natural vocabulary for a SQL query, while
    ``page``/``size`` is the natural vocabulary for an API client
    ("give me page 2"). The conversion between the two happens once, in
    :func:`_paginate`, rather than being duplicated in every endpoint.

    Deliberately a thin data container with no computed convenience
    properties (``has_next``, ``pages``, etc.) beyond what's already
    here — a client that needs "is there a next page" can compare
    ``page * size < total``, and adding derived fields here risks them
    drifting out of sync with ``total``/``size`` if either is ever
    patched independently (e.g. by a caching layer).
    """

    items: list[ItemSchema]
    total: int
    page: int
    size: int


def _paginate(page: int, size: int) -> tuple[int, int]:
    """
    Convert a 1-indexed ``(page, size)`` pair into the ``(skip, limit)``
    the repository layer expects.

    ``page`` is 1-indexed (page 1 is the first page) since that's the
    more common convention for an end-user-facing API parameter; the
    repository/base-class layer's ``skip``/``limit`` remains 0-indexed
    offset/count, since that maps directly onto SQL's ``OFFSET``/``LIMIT``.
    Callers should treat ``page < 1`` as ``page = 1`` (endpoints are
    expected to enforce this via ``Query(ge=1, ...)``; this helper does
    not re-validate it).
    """

    skip = (page - 1) * size
    return skip, size


class BaseService(Generic[ModelType, CreateSchema, UpdateSchema, ResponseSchema, BriefSchema]):
    """
    Generic CRUD orchestration shared by feature services.

    ``BaseService`` implements the standard "fetch → validate → persist →
    serialize" flow on top of a :class:`BaseRepository`, so that a feature
    service only needs to supply its model, its Pydantic schemas, and its
    own "not found" exception. Feature-specific behavior (uniqueness
    checks, extra lookups, side effects, etc.) is added by subclassing and
    extending or overriding the methods below — the base class covers the
    plain CRUD case, not every case.

    Type parameters:
        ModelType: The SQLAlchemy model handled by the underlying
            repository (must satisfy ``ModelProtocol``, i.e. expose ``id``).
        CreateSchema: Pydantic schema accepted by :meth:`create`. Its
            ``model_dump()`` output is passed straight to
            ``repository.create``.
        UpdateSchema: Pydantic schema accepted by :meth:`update`. Only
            fields explicitly set on the instance
            (``model_dump(exclude_unset=True)``) are applied, so partial
            updates work without extra logic in feature services.
        ResponseSchema: Pydantic schema used to serialize model instances
            for the caller. Every public method returns this type (or a
            list of it), so persistence details never leak past the
            service boundary.
        BriefSchema: Optional Pydantic schema used by :meth:`list_brief`
            for lightweight listing views. Its field names double as the
            column names to select from the model (see ``brief_schema``
            below) — if a feature never calls :meth:`list_brief`, this can
            be left as ``BaseModel`` and ``brief_schema`` omitted.

    Example:
        Wiring the base class into a concrete feature service::

            class SpellService(
                BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellBriefResponse]
            ):
                def __init__(self, db: Session):
                    super().__init__(
                        repository=SpellRepository(db),
                        response_schema=SpellResponse,
                        not_found_exception_factory=lambda spell_id: SpellNotFoundException(
                            spell_id=spell_id
                        ),
                        brief_schema=SpellBriefResponse,

        ``not_found_exception_factory`` receives the missing ``item_id``
        and must return (not raise) an ``Exception`` instance; the base
        class raises it on the caller's behalf inside :meth:`_get_or_404`.
        This lets each feature surface its own HTTP exception (e.g. a
        FastAPI ``HTTPException`` subclass) while sharing the lookup logic.

    """

    def __init__(
        self,
        repository: BaseRepository[ModelType],
        response_schema: type[ResponseSchema],
        brief_schema: type[BriefSchema] | None = None,
    ):
        self.repository = repository
        self.response_schema = response_schema
        self.brief_schema = brief_schema

    def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[ResponseSchema]:
        """
        Return a page of records, serialized to ``ResponseSchema``, wrapped
        in a ``Page`` envelope with ``total`` (the count across every page,
        not just this one).

        Args:
            page: 1-indexed page number.
            size: Maximum number of records per page.
            filters: Optional exact-match filters, passed straight through
                to ``repository.get_all`` — see
                ``BaseRepository._apply_filters`` for the exact semantics
                (only keys naming an actual model attribute, with a
                non-``None`` value, are applied). Lets a feature's filtered
                listing (e.g. ``GET /features/?class_id=3``) go through
                this method instead of writing its own service method, as
                long as the filtering is plain exact-match — a feature
                needing anything more (ranges, a different sort together
                with the filter) still overrides :meth:`get_all` itself,
                the same as before.
            search: Optional case-insensitive substring match, passed
                straight through to ``repository.get_all`` — see
                ``BaseRepository._apply_search`` for the exact semantics
                (Or's across the repository's ``search_fields``, either
                pinned at construction or auto-detected from the model's
                text columns). Combines with ``filters`` (Anand together).
                A repository with no searchable fields (``search_fields=[]``)
                silently ignores this.

        ``total`` is computed via ``repository.count(filters=filters,
        search=search)`` — a second query using the *same* conditions as
        the page fetch, minus ``skip``/``limit`` — so it reflects "how many
        records match this filter/search", not the table's grand total.

        """

        skip, limit = _paginate(page, size)
        items = self.repository.get_all(skip=skip, limit=limit, filters=filters, search=search)
        total = self.repository.count(filters=filters, search=search)

        return Page(
            items=[self.response_schema.model_validate(item) for item in items],
            total=total,
            page=page,
            size=size,
        )

    def get_by_id(self, item_id: int) -> ResponseSchema:
        """Return a single record by ID, or raise the feature's not-found exception."""

        item = self._get_or_404(item_id)
        return self.response_schema.model_validate(item)

    def list_brief(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[BriefSchema]:
        """
        Return a paginated, lightweight listing of records, wrapped in a
        ``Page`` envelope with ``total``.

        The columns selected are derived from ``brief_schema``: every field
        name declared on it is looked up as an attribute on ``ModelType``
        and selected directly (no relationship loading, no full model
        instantiation), so this stays cheap even for a wide model with
        expensive relationships. Rows are ordered by the model's ``id``.

        Requires ``brief_schema`` to have been passed to ``__init__``;
        raises ``ValueError`` otherwise, since there'd be no schema to
        derive columns from or validate rows against.

        Args:
            page: 1-indexed page number.
            size: Maximum number of records per page.
            filters: Optional exact-match filters, passed straight through
                to ``repository.get_brief`` — same semantics as on
                :meth:`get_all`. The filter conditions are checked against
                ``self.repository.model``'s attributes, not against the
                selected brief columns, so a field can be filtered on even
                if it isn't part of ``brief_schema``.
            search: Optional case-insensitive substring match, passed
                straight through to ``repository.get_brief`` — same
                semantics as on :meth:`get_all`. Like ``filters``, this is
                checked against ``self.repository.model``'s attributes
                (the repository's ``search_fields``), not against the
                selected brief columns, so a field can be searched even if
                it isn't part of ``brief_schema``.

        ``total`` uses the same ``repository.count(filters=filters,
        search=search)`` as :meth:`get_all` — the brief listing and the
        full listing always agree on how many records match, since they
        share the same underlying ``self.repository.model`` and the same
        filter/search conditions; only the selected columns differ.

        """

        if self.brief_schema is None:
            raise ValueError(f"{type(self).__name__}.list_brief() requires 'brief_schema' to be set in __init__.")

        model = self.repository.model
        columns = [getattr(model, field_name) for field_name in self.brief_schema.model_fields]

        skip, limit = _paginate(page, size)
        rows = self.repository.get_brief(
            *columns, order_by=model.id, skip=skip, limit=limit, filters=filters, search=search
        )
        total = self.repository.count(filters=filters, search=search)

        return Page(
            items=[self.brief_schema.model_validate(row, from_attributes=True) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    def create(self, create_data: CreateSchema) -> ResponseSchema:
        """
        Persist a new record from ``create_data`` and return it serialized.

        Note this performs no uniqueness or business-rule validation on its
        own; add that in a subclass override before calling
        ``super().create(...)`` if the feature requires it.
        """

        try:
            item = self.repository.create(create_data.model_dump())
            return self.response_schema.model_validate(item)
        except RecordAlreadyExistsError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    def update(
        self,
        item_id: int,
        update_data: UpdateSchema,
        *,
        before_update: BeforeUpdateHook | None = None,
    ) -> ResponseSchema:
        """
        Partially update a record and return it serialized.

        Only fields explicitly set on ``update_data`` are applied
        (``exclude_unset=True``), so omitted fields are left untouched.
        Raises the feature's not-found exception if ``item_id`` doesn't exist.

        Args:
            item_id: ID of the record to update.
            update_data: Schema instance with the fields to apply.
            before_update: Optional hook run after the record is fetched
                but before it's persisted, as
                ``before_update(item, fields)`` where ``fields`` is the
                already-computed ``exclude_unset=True`` dict. Lets a
                feature service add validation that needs the current
                record (e.g. a uniqueness check that only fires when a
                field is actually changing) without re-fetching the item
                or re-deriving ``fields`` itself. The hook may raise to
                abort the update; its return value is ignored, though it
                may mutate ``fields`` in place if it needs to adjust what
                gets persisted.

        """

        item = self._get_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)

        if before_update:
            before_update(item, fields)

        try:
            updated_item = self.repository.update(item, fields)
            return self.response_schema.model_validate(updated_item)
        except RecordAlreadyExistsError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    def delete(self, item_id: int) -> bool:
        """
        Delete a record by ID, returning ``True`` on success.

        Raises the feature's not-found exception if ``item_id`` doesn't exist.
        """

        item = self._get_or_404(item_id)
        return self.repository.delete(item)

    def _get_or_404(self, item_id: int) -> ModelType:
        """Fetch the raw model instance or raise the feature's not-found exception."""

        item = self.repository.get_by_id(item_id)
        if not item:
            raise RecordNotFoundError(model_name=self.repository.model.__name__, id=str(item_id))

        return item

    @staticmethod
    def resolve_ids(items: list, requested_ids: list[int]) -> tuple[list, list[int]]:
        """
        Split ``requested_ids`` into what was actually found vs. what's missing.

        Generic replacement for the repeated "resolve IDs → collect missing"
        pattern that shows up per-feature (e.g. what used to be
        ``ClassService._resolve_skill_ids``, ``RaceService._resolve_skill_ids``,
        ``SpellService._resolve_class_ids``/``_resolve_race_ids``): a feature
        service looks up a batch of related records by ID via its own
        repository method (the *lookup* stays feature-specific — different
        model, different table, e.g. ``repository.get_skills_by_ids``), then
        calls this to figure out which of the requested IDs didn't resolve.

        A ``staticmethod`` rather than an instance method since it doesn't
        touch ``self.repository`` — the items are already fetched by the
        time this is called, so nothing here is model-specific.

        Args:
            items: Already-fetched related records (each must expose ``id``).
            requested_ids: The IDs that were asked for.

        Returns:
            ``(items, missing_ids)`` — ``items`` is passed through unchanged
            (so call sites can keep unpacking both, same as before),
            ``missing_ids`` preserves the order of ``requested_ids``.

        Example:
            Replacing a feature-local resolver::

                def _resolve_skill_ids(self, skill_ids: list[int]):
                    skills = self.repository.get_skills_by_ids(skill_ids)
                    return self.resolve_ids(skills, skill_ids)

            Or calling it directly at the use site without even keeping
            the wrapper::

                skills = self.repository.get_skills_by_ids(class_data.available_skills)
                skills, missing_ids = self.resolve_ids(skills, class_data.available_skills)

        """
        found_ids = {item.id for item in items}
        missing_ids = [requested_id for requested_id in requested_ids if requested_id not in found_ids]
        return items, missing_ids

    def _resolve_or_raise(
        self, lookup_fn: Callable[[list[int]], list], ids: list[int], exception_cls: type[Exception]
    ) -> list:
        """
        Resolve `ids` via `lookup_fn`, raising `exception_cls(missing_ids)` if any
        don't resolve. Thin wrapper around `resolve_ids` to eliminate boilerplate
        across feature services.
        """
        if not ids:
            return []

        found = lookup_fn(ids)
        items, missing_ids = self.resolve_ids(found, ids)
        if missing_ids:
            raise exception_cls(missing_ids)
        return items

    @contextmanager
    def _atomic(self) -> Generator[None, None, None]:
        """
        Wrap a multistep creation/write inside a single all-or-nothing transaction.

        Generic replacement for the repeated ``begin_nested()`` +
        ``commit=False`` + ``rollback``-on-``except`` block that shows up in
        every feature's "create the record plus its association-table rows
        together" method (e.g. what used to be duplicated across
        ``ClassService.create_class``, ``RaceService.create_race``,
        ``SpellService.create_spell``).

        Every repository write performed inside the ``with`` block MUST
        pass ``commit=False`` (including the initial ``repository.create``
        call) — a plain ``session.commit()`` from any of them would commit
        the *entire* outer transaction, not just this method's
        ``begin_nested()`` SAVEPOINT, leaving the ``begin_nested()`` context
        manager holding a reference to an already-closed transaction and
        raising ``Can't operate on closed transaction`` on exit. This is
        the same hazard documented on ``BaseRepository.create``.

        On success, commits once after the ``with`` block exits. On any
        exception, rolls back and re-raises — callers don't need their own
        try/except around this.

        Note this does *not* call ``self.repository.db.refresh(item)``
        afterward — refreshing isn't part of the write transaction itself,
        and the caller doesn't have ``item`` in scope from inside a
        ``@contextmanager``. Call ``refresh`` explicitly after the ``with``
        block if the caller needs autogenerated fields reloaded.

        Example:
            ::

                def create_class(self, class_data: ClassCreate, ...) -> ClassResponse:
                    ...
                    with self._atomic():
                        item = self.repository.create(payload, commit=False)
                        if class_data.primary_abilities:
                            self.repository.set_primary_abilities(
                                item, class_data.primary_abilities, commit=False
                            )
                        ...
                    self.repository.db.refresh(item)
                    return self.response_schema.model_validate(item)

        """
        db = self.repository.db
        try:
            with db.begin_nested():
                yield
            db.commit()
        except Exception:
            db.rollback()
            raise
