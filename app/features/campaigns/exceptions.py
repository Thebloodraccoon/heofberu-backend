"""Exceptions of the game campaigns domain."""

from app.core.exceptions import AppError


class CampaignNotFoundException(AppError):
    """
    Raised (404) when a campaign doesn't exist OR the caller may not see it.

    A campaign is private to its GM, its players and the founder; for anyone else it doesn't exist, so a 403 would
    leak that it does.
    """

    status_code = 404

    def __init__(self, campaign_id: int):
        """Initialize with the requested campaign id."""

        self.campaign_id = campaign_id
        super().__init__(f"Campaign {campaign_id} not found.")


class CampaignGmOnlyException(AppError):
    """Raised (403) when a player of the campaign tries something only its GM (or the founder) may do."""

    status_code = 403

    def __init__(self, campaign_id: int):
        """Initialize with the campaign id."""

        self.campaign_id = campaign_id
        super().__init__(f"Only the GM of campaign {campaign_id} can do this.")


class CampaignPlayerOnlyException(AppError):
    """Raised (403) when someone who has no character in the campaign tries to review it or its sessions."""

    status_code = 403

    def __init__(self, campaign_id: int):
        """Initialize with the campaign id."""

        self.campaign_id = campaign_id
        super().__init__(f"Only players of campaign {campaign_id} can write reviews.")


class CampaignClosedException(AppError):
    """Raised (409) when characters are added to a finished, abandoned or archived campaign."""

    status_code = 409

    def __init__(self, campaign_id: int):
        """Initialize with the campaign id."""

        self.campaign_id = campaign_id
        super().__init__(f"Campaign {campaign_id} is closed: reopen it (status) or restore it from the archive first.")


class CharacterNotFreeException(AppError):
    """Raised (409) when a character added to a campaign is already active in one (it can be in one at a time)."""

    status_code = 409

    def __init__(self, character_id: int):
        """Initialize with the character id."""

        self.character_id = character_id
        super().__init__(f"Character {character_id} already plays in a campaign; it must be released there first.")


class CampaignCharacterNotFoundException(AppError):
    """Raised (404) when a participation id doesn't belong to the campaign."""

    status_code = 404

    def __init__(self, campaign_id: int, participation_id: int):
        """Initialize with the campaign and participation ids."""

        self.campaign_id = campaign_id
        self.participation_id = participation_id
        super().__init__(f"Campaign {campaign_id} has no character participation {participation_id}.")


class CampaignCharacterStatusException(AppError):
    """Raised (409) for a participation status change that isn't allowed (see ``characters.service``)."""

    status_code = 409

    def __init__(self, participation_id: int, current: str, target: str):
        """Initialize with the participation and the rejected move."""

        self.participation_id = participation_id
        super().__init__(
            f"Participation {participation_id} can't go from {current} to {target}: "
            "only an active character changes status (or anything can be removed); re-add a character to bring it back."
        )


class CampaignSessionNotFoundException(AppError):
    """Raised (404) when a session doesn't exist in the campaign."""

    status_code = 404

    def __init__(self, campaign_id: int, session_id: int):
        """Initialize with the campaign and session ids."""

        self.campaign_id = campaign_id
        self.session_id = session_id
        super().__init__(f"Campaign {campaign_id} has no session {session_id}.")


class CampaignSessionNotPublishedException(AppError):
    """Raised (409) when a player reviews a session whose chronicle the GM hasn't published yet."""

    status_code = 409

    def __init__(self, session_id: int):
        """Initialize with the session id."""

        self.session_id = session_id
        super().__init__(f"Session {session_id} can be reviewed once its chronicle is published.")


class CampaignOwnReviewException(AppError):
    """Raised (403) when the campaign's GM tries to review their own campaign (also when playing in it)."""

    status_code = 403

    def __init__(self, campaign_id: int):
        """Initialize with the campaign id."""

        self.campaign_id = campaign_id
        super().__init__(f"The GM of campaign {campaign_id} doesn't review it.")


class CampaignReviewHiddenException(AppError):
    """Raised (409) when the author edits a campaign or session review the founder has hidden (delete still works)."""

    status_code = 409

    def __init__(self, campaign_id: int):
        """Initialize with the campaign id."""

        self.campaign_id = campaign_id
        super().__init__(f"Your review in campaign {campaign_id} was hidden by moderation and can't be edited.")


class CampaignListFilterException(AppError):
    """Raised (400) when ``role`` is combined with the founder's ``all_campaigns`` view."""

    status_code = 400

    def __init__(self):
        """No arguments: the message says which filters clash."""

        super().__init__("`role` filters the caller's own campaigns; it can't be combined with `all_campaigns`.")


class CampaignNoteNotFoundException(AppError):
    """Raised (404) when a note doesn't exist in the campaign."""

    status_code = 404

    def __init__(self, campaign_id: int, note_id: int):
        """Initialize with the campaign and note ids."""

        self.campaign_id = campaign_id
        self.note_id = note_id
        super().__init__(f"Campaign {campaign_id} has no note {note_id}.")


class CampaignReviewNotFoundException(AppError):
    """Raised (404) when a review doesn't exist."""

    status_code = 404

    def __init__(self, review_id: int | None = None):
        """Initialize with the review id (``None``: "your review" of a campaign/session, which doesn't exist)."""

        self.review_id = review_id
        super().__init__(f"Review {review_id} not found." if review_id is not None else "You have no review here.")


class PublicCampaignLinkNotFoundException(AppError):
    """Raised (400) when a campaign is made from / linked to a preset that doesn't exist or isn't visible."""

    status_code = 400

    def __init__(self, public_campaign_id: int):
        """Initialize with the public campaign id."""

        self.public_campaign_id = public_campaign_id
        super().__init__(f"Public campaign {public_campaign_id} doesn't exist or isn't published.")
