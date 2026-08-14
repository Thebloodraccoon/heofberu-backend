"""Class-scoped ownership checks shared by the subclass subdomain services."""

from app.core.exceptions import RecordNotFoundError
from app.features.classes.exceptions import SubclassNotFoundException
from app.models.subclass_model import Subclass


class SubclassScopedMixin:
    """
    Turn "wrong class" into the same 404 a caller would get for a missing subclass.

    Requires the host service to provide ``_get_or_404`` (from
    :class:`BaseService`); the raw fetch is delegated to it so the base's
    generic ``RecordNotFoundError`` is translated into the class-scoped
    :class:`SubclassNotFoundException` rather than re-implemented here.
    """

    async def _get_or_404_for_class(self, class_id: int, subclass_id: int) -> Subclass:
        """
        Fetch the raw ``Subclass`` instance, raising ``SubclassNotFoundException``
        if it's missing or belongs to a different class.
        """

        try:
            subclass = await self._get_or_404(subclass_id)
        except RecordNotFoundError as exc:
            raise SubclassNotFoundException(class_id=class_id, subclass_id=subclass_id) from exc

        if subclass.class_id != class_id:
            raise SubclassNotFoundException(class_id=class_id, subclass_id=subclass_id)

        return subclass
