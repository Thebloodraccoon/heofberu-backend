from collections.abc import Callable
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.core.repository import BaseRepository, ModelType

CreateSchema = TypeVar("CreateSchema", bound=BaseModel)
UpdateSchema = TypeVar("UpdateSchema", bound=BaseModel)
ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)

NotFoundExceptionFactory = Callable[[int], Exception]


class BaseService(Generic[ModelType, CreateSchema, UpdateSchema, ResponseSchema]):
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

    Example:
        Wiring the base class into a concrete feature service::

            class SpellService(BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse]):
                def __init__(self, db: Session):
                    super().__init__(
                        repository=SpellRepository(db),
                        response_schema=SpellResponse,
                        not_found_exception_factory=lambda spell_id: SpellNotFoundException(
                            spell_id=spell_id
                        )
                    )

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
        not_found_exception_factory: NotFoundExceptionFactory,
    ):
        self.repository = repository
        self.response_schema = response_schema
        self._not_found_exception_factory = not_found_exception_factory

    def get_all(self, skip: int = 0, limit: int = 100) -> list[ResponseSchema]:
        """
        Return a page of records, serialized to ``ResponseSchema``.

        Args:
            skip: Number of records to skip (offset-based pagination).
            limit: Maximum number of records to return.

        """

        items = self.repository.get_all(skip=skip, limit=limit)
        return [self.response_schema.model_validate(item) for item in items]

    def get_by_id(self, item_id: int) -> ResponseSchema:
        """Return a single record by ID, or raise the feature's not-found exception."""

        item = self._get_or_404(item_id)
        return self.response_schema.model_validate(item)

    def create(self, create_data: CreateSchema) -> ResponseSchema:
        """
        Persist a new record from ``create_data`` and return it serialized.

        Note this performs no uniqueness or business-rule validation on its
        own; add that in a subclass override before calling
        ``super().create(...)`` if the feature requires it.
        """

        item = self.repository.create(create_data.model_dump())
        return self.response_schema.model_validate(item)

    def update(self, item_id: int, update_data: UpdateSchema) -> ResponseSchema:
        """
        Partially update a record and return it serialized.

        Only fields explicitly set on ``update_data`` are applied
        (``exclude_unset=True``), so omitted fields are left untouched.
        Raises the feature's not-found exception if ``item_id`` doesn't exist.
        """

        item = self._get_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)
        updated_item = self.repository.update(item, fields)
        return self.response_schema.model_validate(updated_item)

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
            raise self._not_found_exception_factory(item_id)

        return item
