"""Feat-specific application exceptions."""

from app.core.exceptions import AppError


class FeatNotFoundException(AppError):
    """Raised when a feat with the given ID does not exist."""

    status_code = 404

    def __init__(self, feat_id: int):
        self.feat_id = feat_id
        super().__init__(f"Feat with id {feat_id} not found.")
