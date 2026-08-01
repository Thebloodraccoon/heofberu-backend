from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.items.exceptions import ItemInUseException, ItemNameAlreadyExistsException, ItemNotFoundException
from app.features.items.repository import ItemRepository
from app.features.items.schemas import ItemBriefResponse, ItemCreate, ItemResponse, ItemUpdate
from app.models.item_model import Item


class ItemService(BaseService[Item, ItemCreate, ItemUpdate, ItemResponse, ItemBriefResponse]):
    """
    Item-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - a delete guard that blocks removing an item still owned by any
        character, since the FK on ``character_items.item_id`` is
        ``ON DELETE RESTRICT`` (unlike Background, whose FK is
        ``SET NULL`` — see ``BackgroundService`` for the contrasting case).

    ``get_by_id`` and ``list_brief`` are inherited unchanged from
    ``BaseService`` — items add no relationship fields on top of them, so
    the generic column-select ``list_brief`` works as-is (contrast with
    ``SpellService``/``BackgroundService``, which override it because
    their brief schemas include relationship fields). ``delete`` is
    overridden as ``delete_item`` to add the in-use guard; endpoints
    should call ``delete_item``, not the inherited ``delete``.
    """

    repository: ItemRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=ItemRepository(db),
            response_schema=ItemResponse,
            not_found_exception_factory=lambda item_id: ItemNotFoundException(item_id=item_id),
            brief_schema=ItemBriefResponse,
        )

    def create_item(self, item_data: ItemCreate, created_by_id: int | None = None) -> ItemResponse:
        """
        Create an item after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant
        mainly for homebrew items) and is not part of ``ItemCreate``
        itself, since it comes from the authenticated user, not client
        input.
        """

        self._check_name_available(item_data.name)

        payload = item_data.model_dump()
        payload["created_by_id"] = created_by_id

        item = self.repository.create(payload)
        return self.response_schema.model_validate(item)

    def update_item(self, item_id: int, update_data: ItemUpdate) -> ItemResponse:
        """Update an item, re-checking name uniqueness if the name is changing."""

        def check_name_available_if_changing(item: Item, fields: dict) -> None:
            if "name" in fields and fields["name"] != item.name:
                self._check_name_available(fields["name"])

        return self.update(item_id, update_data, before_update=check_name_available_if_changing)

    def delete_item(self, item_id: int) -> bool:
        """
        Delete an item by ID, raising ``ItemInUseException`` if it's still
        owned by any character.

        Raises the feature's not-found exception if ``item_id`` doesn't
        exist. The in-use check happens before deletion, with an
        ``IntegrityError`` safety net in case of a race condition between
        the check and the actual delete (the FK is ``ON DELETE RESTRICT``).
        """
        item = self._get_or_404(item_id)

        if self.repository.is_in_use(item_id):
            raise ItemInUseException(item_id=item_id)

        try:
            return self.repository.delete(item)
        except IntegrityError:
            self.repository.db.rollback()
            raise ItemInUseException(item_id=item_id)

    def _check_name_available(self, name: str) -> None:
        """Raise ``ItemNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise ItemNameAlreadyExistsException(name)
