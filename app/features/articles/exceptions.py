"""Exceptions shared across the articles domain."""

from app.core.exceptions import AppError


class ArticleParentCycleException(AppError):
    """Raised when an article would become its own ancestor (parent is itself or one of its descendants)."""

    status_code = 400

    def __init__(self, article_id: int, parent_id: int):
        """Initialize with the article and the rejected parent ids."""

        self.article_id = article_id
        self.parent_id = parent_id
        super().__init__(f"Article {parent_id} cannot be the parent of article {article_id}: it would create a cycle.")


class ArticleTreeTooDeepException(AppError):
    """Raised (400) when placing an article would push its subtree past the supported nesting depth."""

    status_code = 400

    def __init__(self, article_id: int, max_depth: int):
        """Initialize with the article being placed and the maximum tree depth."""

        self.article_id = article_id
        self.max_depth = max_depth
        super().__init__(
            f"Article {article_id} cannot be placed there: the tree may be at most {max_depth} levels deep."
        )


class ArticleStatusTransitionException(AppError):
    """Raised (409) when a review-workflow action isn't allowed from the article's current status."""

    status_code = 409

    def __init__(self, article_id: int, action: str, current_status: str):
        """Initialize with the article, the rejected action and the status it was attempted from."""

        self.article_id = article_id
        self.action = action
        self.current_status = current_status
        super().__init__(f"Cannot {action} article {article_id}: it is {current_status}.")


class ArticleVersionMismatchException(AppError):
    """Raised (409) when an article is published at a version other than the current one (it was edited meanwhile)."""

    status_code = 409

    def __init__(self, article_id: int, expected: int, current: int):
        """Initialize with the article, the version the reviewer confirmed and its actual current version."""

        self.article_id = article_id
        self.expected = expected
        self.current = current
        super().__init__(
            f"Article {article_id} is at version {current}, not {expected}: it was edited after you reviewed it. "
            f"Review the changes (GET /articles/{article_id}/revisions/{current}/diff) and publish again."
        )


class ArticleEditForbiddenException(AppError):
    """Raised (403) when a GM edits an article they didn't write: they may only propose changes to it."""

    status_code = 403

    def __init__(self, article_id: int):
        """Initialize with the article the caller may not edit."""

        self.article_id = article_id
        super().__init__(f"You can only edit your own articles; article {article_id} belongs to someone else.")


class ArticleSubtypeTypeMismatchException(AppError):
    """Raised (400) when an article would use a subtype of a different ``article_type``."""

    status_code = 400

    def __init__(self, subtype_id: int, subtype_type: str, article_type: str):
        """Initialize with the subtype, the type it belongs to and the article's type."""

        self.subtype_id = subtype_id
        super().__init__(
            f"Subtype {subtype_id} belongs to article_type '{subtype_type}', not '{article_type}'. "
            "Change or clear subtype_id together with article_type."
        )


class ArticleProposalNotNeededException(AppError):
    """Raised (409) when the article's author proposes a change: they edit the article directly."""

    status_code = 409

    def __init__(self, article_id: int):
        """Initialize with the article the caller may edit."""

        self.article_id = article_id
        super().__init__(
            f"You can edit article {article_id} directly (PATCH /articles/{article_id}); no proposal needed."
        )


class ArticleProposalClosedException(AppError):
    """Raised (409) when accepting/rejecting a proposal that was already accepted or rejected."""

    status_code = 409

    def __init__(self, proposal_id: int, status: str):
        """Initialize with the proposal and its current status."""

        self.proposal_id = proposal_id
        super().__init__(f"Proposal {proposal_id} is already {status}.")


class ArticleProposalStaleException(AppError):
    """Raised (409) when accepting a proposal made against an older version (the article was edited since)."""

    status_code = 409

    def __init__(self, proposal_id: int, base_version: int, current: int):
        """Initialize with the proposal, the version it was based on and the article's current version."""

        self.proposal_id = proposal_id
        self.base_version = base_version
        self.current = current
        super().__init__(
            f"Proposal {proposal_id} was made against version {base_version}, but the article is at version "
            f"{current}. Reject it, and the proposer can propose again on top of the current version."
        )


class ArticleProposalWithdrawForbiddenException(AppError):
    """Raised (403) when someone other than the proposer tries to withdraw a proposal."""

    status_code = 403

    def __init__(self, proposal_id: int):
        """Initialize with the proposal the caller may not withdraw."""

        self.proposal_id = proposal_id
        super().__init__(f"Only the GM who made proposal {proposal_id} can withdraw it.")


class ArticleProposalChangeForbiddenException(AppError):
    """Raised (403) when someone other than the proposer, the article's author or the founder changes a proposal."""

    status_code = 403

    def __init__(self, proposal_id: int):
        """Initialize with the proposal the caller may not change."""

        self.proposal_id = proposal_id
        super().__init__(
            f"Only the GM who made proposal {proposal_id}, the article's author or the founder can update it."
        )


class ArticleProposalConflictException(AppError):
    """Raised (409) when a proposal can't be merged onto the current version: both sides changed the same thing."""

    status_code = 409

    def __init__(self, proposal_id: int, details: dict):
        """Initialize with the proposal and the conflicts (``conflicts``, ``body_conflicts``, ``merged_body``)."""

        self.proposal_id = proposal_id
        super().__init__(
            f"Proposal {proposal_id} conflicts with the current version of the article: resolve the conflicts and "
            f"PUT the result (base_version = the current version).",
            details=details,
        )
