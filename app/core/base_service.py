from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Generic

from pydantic import BaseModel
from typing_extensions import TypeVar

from app.core.base_repository import BaseRepository, ModelType
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError

CreateSchema = TypeVar("CreateSchema", bound=BaseModel)
UpdateSchema = TypeVar("UpdateSchema", bound=BaseModel)
ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)
BriefSchema = TypeVar("BriefSchema", bound=BaseModel, default=BaseModel)
BeforeUpdateHook = Callable[[ModelType, dict], None]

ItemSchema = TypeVar("ItemSchema", bound=BaseModel)
ResolvedItem = TypeVar("ResolvedItem")


class Page(BaseModel, Generic[ItemSchema]):
    """Generic ``{items, total, page, size}`` envelope for a paginated listing."""

    items: list[ItemSchema]
    total: int
    page: int
    size: int


def _paginate(page: int, size: int) -> tuple[int, int]:
    """Convert a 1-indexed ``(page, size)`` into the repository's 0-indexed ``(skip, limit)``."""

    skip = (page - 1) * size
    return skip, size


class BaseService(Generic[ModelType, CreateSchema, UpdateSchema, ResponseSchema, BriefSchema]):
    """
    Generic "fetch → validate → persist → serialize" CRUD orchestration on
    top of a :class:`BaseRepository`.

    Type parameters:
        ModelType: SQLAlchemy model handled by the repository.
        CreateSchema: Schema accepted by :meth:`create`.
        UpdateSchema: Schema accepted by :meth:`update` (partial update).
        ResponseSchema: Schema used to serialize results.
        BriefSchema: Optional schema for :meth:`list_brief`.

    Example::

        class SpellService(
            BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellBriefResponse]
        ):
            def __init__(self, db: Session):
                super().__init__(
                    repository=SpellRepository(db),
                    response_schema=SpellResponse,
                    brief_schema=SpellBriefResponse,
                )
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
        Return a page of records serialized to ``ResponseSchema``.

        Args:
            page: 1-indexed page number.
            size: Records per page.
            filters: Exact-match filters, passed to ``repository.get_all``.
            search: Substring match, passed to ``repository.get_all``.
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
        """Return a single record by ID, or raise ``RecordNotFoundError``."""

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
        Return a paginated, lightweight listing using ``brief_schema``'s fields as columns.

        Requires ``brief_schema`` to have been set in ``__init__``.
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
        """Persist a new record and return it serialized. No business-rule validation is done here."""

        item = self.repository.create(create_data.model_dump())
        return self.response_schema.model_validate(item)

    def update(
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

        item = self._get_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)

        if before_update:
            before_update(item, fields)

        updated_item = self.repository.update(item, fields)
        return self.response_schema.model_validate(updated_item)

    def delete(self, item_id: int) -> bool:
        """
        Delete a record by ID, returning ``True`` on success.

        If the repository was constructed with ``check_in_use_on_delete=True``,
        ``self.repository.delete`` itself raises ``RecordInUseError`` when
        the record is still referenced elsewhere -- no extra handling
        needed here; see ``BaseRepository.delete``/``is_in_use``.
        """
        item = self._get_or_404(item_id)
        return self.repository.delete(item)

    def _get_or_404(self, item_id: int) -> ModelType:
        """Fetch the raw model instance or raise ``RecordNotFoundError``."""

        item = self.repository.get_by_id(item_id)
        if not item:
            raise RecordNotFoundError(model_name=self.repository.model.__name__, model_id=str(item_id))

        return item

    @staticmethod
    def resolve_ids(
        lookup_fn: Callable[[list[int]], list[ResolvedItem]], ids: list[int], model_name: str
    ) -> list[ResolvedItem]:
        """Resolve ``ids`` via ``lookup_fn``, raising ``RecordIdsInvalidError`` if any don't resolve."""

        if not ids:
            return []

        founds = lookup_fn(ids)
        found_ids = {found.id for found in founds}
        missing_ids = [item_id for item_id in ids if item_id not in found_ids]

        if missing_ids:
            raise RecordIdsInvalidError(model_name=model_name, ids=missing_ids)

        return founds

    @contextmanager
    def _atomic(self) -> Generator[None, None, None]:
        """
        Wrap a multistep write in a single all-or-nothing transaction.

        Every repository write inside the ``with`` block MUST pass
        ``commit=False``. Commits once on success; rolls back and
        re-raises on any exception.

        See also: ``BaseRepository._commit_or_rollback`` for the single-write
        case — use that (indirectly, via ``commit=True``) when only one
        repository call is involved; use ``_atomic()`` when more than one is.

        Example::

            with self._atomic():
                item = self.repository.create(payload, commit=False)
                ...
            self.repository.db.refresh(item)
        """
        db = self.repository.db
        try:
            with db.begin_nested():
                yield
            db.commit()
        except Exception:
            db.rollback()
            raise
