"""Exceptions of the public campaigns (presets) domain."""

from app.core.exceptions import AppError


class PublicCampaignNotFoundException(AppError):
    """Raised (404) when a public campaign doesn't exist or isn't published (for players and guests)."""

    status_code = 404

    def __init__(self, ref: int | str):
        """Initialize with the requested id or slug."""

        self.ref = ref
        super().__init__(f"Public campaign {ref} not found.")


class PublicCampaignEditForbiddenException(AppError):
    """Raised (403) when someone other than the author or the founder changes a public campaign."""

    status_code = 403

    def __init__(self, public_campaign_id: int):
        """Initialize with the public campaign id."""

        self.public_campaign_id = public_campaign_id
        super().__init__(f"Only the author of public campaign {public_campaign_id} (or the founder) can change it.")


class PublicCampaignStatusTransitionException(AppError):
    """Raised (409) when a publish/unpublish/archive action isn't allowed from the current status."""

    status_code = 409

    def __init__(self, public_campaign_id: int, action: str, current_status: str):
        """Initialize with the public campaign, the rejected action and its current status."""

        self.public_campaign_id = public_campaign_id
        super().__init__(f"Cannot {action} public campaign {public_campaign_id}: it is {current_status}.")
