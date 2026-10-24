"""
Who may do what in a game campaign: the one place campaign permissions are decided.

Three kinds of viewers, resolved once per request into a ``CampaignContext``:

* the **owner** (the campaign's GM) and the **founder**: everything (``is_gm``);
* a **player**: anyone with a character in the campaign whose participation isn't ``REMOVED``. Reads the player
  view (``:::gm`` blocks stripped, a session's chronicle only once published) and writes reviews (the campaign's
  own GM never does, even with a character in it). The player is never asked when added and can't leave;
* anyone else, including other GMs: the campaign doesn't exist for them (404).

The decision is a pure function of ``(user, owner_id, is_player)``; the repository fetches those two facts in one
query (``CampaignAccessMixin.access_row``). Endpoints never compare ids themselves.
"""

from dataclasses import dataclass

from app.constants import UserRole
from app.features.campaigns.exceptions import (
    CampaignGmOnlyException,
    CampaignNotFoundException,
    CampaignOwnReviewException,
    CampaignPlayerOnlyException,
)


@dataclass(frozen=True)
class CampaignContext:
    """The caller's standing in one campaign."""

    campaign_id: int
    user_id: int
    is_owner: bool
    is_founder: bool
    is_player: bool

    @classmethod
    def of(cls, user, campaign_id: int, owner_id: int | None, is_player: bool) -> "CampaignContext":
        """
        Build from an authenticated user (anything with ``id`` and ``role``) and the campaign's access facts.

        ``owner_id`` is ``None`` once the GM's account was deleted: then only the founder acts as its GM.
        """

        return cls(
            campaign_id=campaign_id,
            user_id=user.id,
            is_owner=owner_id is not None and owner_id == user.id,
            is_founder=user.role == UserRole.FOUND_FATHER,
            is_player=is_player,
        )

    @property
    def is_gm(self) -> bool:
        """Full access: the campaign's GM or the founder."""

        return self.is_owner or self.is_founder

    @property
    def can_read(self) -> bool:
        """Whether the campaign exists for this caller at all."""

        return self.is_gm or self.is_player

    @property
    def role(self) -> str:
        """``gm`` or ``player``: which view the responses are built for."""

        return "gm" if self.is_gm else "player"

    def ensure_can_read(self) -> "CampaignContext":
        """404 unless the caller is the GM, the founder or a player of the campaign."""

        if not self.can_read:
            raise CampaignNotFoundException(self.campaign_id)

        return self

    def ensure_gm(self) -> "CampaignContext":
        """404 for outsiders (the campaign stays invisible), 403 for players."""

        self.ensure_can_read()
        if not self.is_gm:
            raise CampaignGmOnlyException(self.campaign_id)

        return self

    def ensure_player(self) -> "CampaignContext":
        """404 for outsiders, 403 for anyone without a character in the campaign."""

        self.ensure_can_read()
        if not self.is_player:
            raise CampaignPlayerOnlyException(self.campaign_id)

        return self

    def ensure_reviewer(self) -> "CampaignContext":
        """A player who isn't the campaign's GM: the owner doesn't review their own table, even when playing in it."""

        self.ensure_player()
        if self.is_owner:
            raise CampaignOwnReviewException(self.campaign_id)

        return self
