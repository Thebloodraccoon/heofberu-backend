"""Feature-specific application exceptions."""

from app.core.exceptions import AppError


class FeatureNotFoundException(AppError):
    """Raised when a feature with the given ID does not exist."""

    status_code = 404

    def __init__(self, feature_id: int):
        """Raise the error naming the offending ``feature_id``."""

        self.feature_id = feature_id
        super().__init__(f"Feature with id {feature_id} not found.")


class InvalidFeatureSourceException(AppError):
    """
    Raised when a feature's source_type/class_id/subclass_id/race_id/
    background_id/level combination is inconsistent (e.g.
    source_type=RACE but race_id is missing).
    """

    status_code = 400

    def __init__(self, detail: str):
        """Raise the error with the given message."""

        super().__init__(detail)
