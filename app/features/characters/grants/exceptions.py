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
    """Raised (422) when an "any skill" option is answered without a concrete skill id."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(
            f"Option {option_id} has an open skill effect — a skill_id must be provided for it."
        )
