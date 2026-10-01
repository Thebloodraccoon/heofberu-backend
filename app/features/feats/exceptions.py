"""Feat-specific application exceptions."""

from app.core.exceptions import AppError


class FeatNotFoundException(AppError):
    """Raised when a feat with the given ID does not exist."""

    status_code = 404

    def __init__(self, feat_id: int):
        """Raise the error naming the offending ``feat_id``."""

        self.feat_id = feat_id
        super().__init__(f"Feat with id {feat_id} not found.")


class FeatPrerequisiteIncompleteError(AppError):
    """Raised (422) when a feat's ability prerequisite would have only one of ability / minimum score."""

    status_code = 422

    def __init__(self):
        """Build the 422 message."""

        super().__init__("prerequisite_ability and prerequisite_minimum_score must be set together.")
