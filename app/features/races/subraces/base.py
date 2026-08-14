"""Race-scoped ownership checks shared by the subrace subdomain services."""

from app.core.exceptions import RecordNotFoundError
from app.features.races.exceptions import SubraceNotFoundException
from app.models.subrace_model import Subrace


class SubraceScopedMixin:
    """
    Turn "wrong race" into the same 404 a caller would get for a missing subrace.

    Requires the host service to provide ``_get_or_404`` (from
    :class:`BaseService`); the raw fetch is delegated to it so the base's
    generic ``RecordNotFoundError`` is translated into the race-scoped
    :class:`SubraceNotFoundException` rather than re-implemented here.
    """

    async def _get_or_404_for_race(self, race_id: int, subrace_id: int) -> Subrace:
        """
        Fetch the raw ``Subrace`` instance, raising ``SubraceNotFoundException``
        if it's missing or belongs to a different race.
        """

        try:
            subrace = await self._get_or_404(subrace_id)
        except RecordNotFoundError as exc:
            raise SubraceNotFoundException(race_id=race_id, subrace_id=subrace_id) from exc

        if subrace.race_id != race_id:
            raise SubraceNotFoundException(race_id=race_id, subrace_id=subrace_id)

        return subrace
