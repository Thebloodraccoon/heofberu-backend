"""Character grant (effect-engine) exceptions."""

from fastapi import status

from app.core.exceptions import AppError


class GrantNotFoundError(AppError):
    """Raised (404) when a character_feature grant doesn't exist for the character."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, character_id: int, grant_id: int):
        """Initialize with both ids for a clear message."""
        super().__init__(f"Feature grant {grant_id} not found on character {character_id}.")


class ChoiceGroupNotFoundError(AppError):
    """Raised (404) when a grant has no such choice group (stale client)."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, grant_id: int, group_id: int):
        """Initialize with the offending ids."""
        super().__init__(f"Choice group {group_id} not found on feature grant {grant_id}.")


class ChoiceOptionNotFoundError(AppError):
    """Raised (404) when a chosen option doesn't belong to the group (stale client)."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, group_id: int, option_id: int):
        """Initialize with the offending ids."""
        super().__init__(f"Choice option {option_id} not found in choice group {group_id}.")


class ChoiceOptionAlreadyPickedError(AppError):
    """Raised (409) when a request re-picks an option already selected for the group."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, group_id: int, option_id: int):
        """Initialize with the offending ids."""
        super().__init__(f"Option {option_id} is already picked for choice group {group_id}.")


class ChoiceCountMismatchError(AppError):
    """Raised (422) when a group is answered with the wrong number of options."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, group_id: int, pick_count: int, given: int):
        """Initialize with the expected vs actual count."""
        super().__init__(
            f"Choice group {group_id} requires exactly {pick_count} option(s); received {given}."
        )


class SkillResolutionsError(AppError):
    """Raised (422) when an "any skill" (open) option is picked — not yet resolvable via the API."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(
            f"Option {option_id} has an open ('any skill') skill effect — picking it isn't supported yet."
        )


class GrantChoiceRequiredException(AppError):
    """
    Raised when a grant (a level-up's newly-unlocked feature, an
    ASI-level feat pick, or a GM-panel feat/feature grant) has a
    "pick N of M" choice group that the caller's answers didn't resolve —
    a grant is never left silently half-materialized regardless of who
    created it.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, feature_id: int, feature_name: str, pending_group_ids: list[int]):
        """Initialize with the unresolved feature/groups."""

        self.feature_id = feature_id
        self.feature_name = feature_name
        self.pending_group_ids = pending_group_ids
        super().__init__(
            f"Feature '{feature_name}' (id {feature_id}) still has unanswered choice group(s) "
            f"{pending_group_ids} — include matching entries in the request's choice answers."
        )


class SpellResolutionsError(AppError):
    """Raised (422) when an "any spell" (open) option is picked — not yet resolvable via the API."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(
            f"Option {option_id} has an open ('any spell') spell effect — picking it isn't supported yet."
        )
