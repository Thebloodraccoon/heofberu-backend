from fastapi import HTTPException, status


class FeatNotFoundException(HTTPException):
    """Raised when a feat with the given ID does not exist."""

    def __init__(self, feat_id: int):
        self.feat_id = feat_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feat with id {feat_id} not found.",
        )

