from fastapi import HTTPException, status


class FeatureNotFoundException(HTTPException):
    """Raised when a feature with the given ID does not exist."""

    def __init__(self, feature_id: int):
        self.feature_id = feature_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature with id {feature_id} not found.",
        )


class InvalidFeatureSourceException(HTTPException):
    """
    Raised when a feature's source_type/class_id/race_id/background_id/level/
    subclass_name combination is inconsistent (e.g. source_type=RACE but
    race_id is missing, or class_id is set alongside source_type=FEAT).
    """

    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
