"""Feature-specific HTTP exceptions."""

from fastapi import HTTPException, status


class InvalidFeatureSourceException(HTTPException):
    """
    Raised when a feature's source_type/class_id/race_id/background_id/feat_id/level/
    subclass_name combination is inconsistent (e.g. source_type=RACE but
    race_id is missing, or class_id is set alongside source_type=FEAT).
    """

    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
