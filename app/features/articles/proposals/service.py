"""
Proposed changes to an article, git-style: a GM who may not edit an article proposes a new version (a pull request
against the current one); its author or the founder accepts it (it becomes the next version, recorded with the
proposer as editor and the acceptor as reviewer) or rejects it (optionally with a reason); the proposer may
withdraw it while it is pending. A proposal left behind by newer versions is rebased onto the current one with a
three-way merge (``revisions.merge``), or its content is replaced by hand after a conflict.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleProposalStatus
from app.core.base.transaction import atomic
from app.core.exceptions import RecordNotFoundError
from app.core.pagination import CursorPage, Page, cursor_page, decode_cursor, paginate
from app.features.articles.access import ArticleActor
from app.features.articles.crud.repository import REVISED_FIELDS
from app.features.articles.crud.schemas import ArticleContentUpdate, ArticleResponse
from app.features.articles.crud.writer import ArticleWriter
from app.features.articles.exceptions import (
    ArticleProposalChangeForbiddenException,
    ArticleProposalClosedException,
    ArticleProposalConflictException,
    ArticleProposalNotNeededException,
    ArticleProposalStaleException,
    ArticleProposalWithdrawForbiddenException,
)
from app.features.articles.proposals.repository import ArticleProposalRepository
from app.features.articles.proposals.schemas import (
    ArticleProposalBrief,
    ArticleProposalReplace,
    ArticleProposalResponse,
    ProposalArticleRef,
)
from app.features.articles.revisions.merge import CONFLICT, merge_text, merge_value
from app.features.articles.revisions.repository import ArticleRevisionRepository
from app.features.articles.revisions.schemas import ArticleRevisionDiff
from app.features.articles.revisions.service import DIFF_FIELDS, build_diff
from app.models.articles.article_proposal_model import ArticleProposal
from app.models.articles.article_revision_model import ArticleRevision

#: ``sort`` name baked into proposal cursors (ordered by id, newest first), so another listing's cursor is a 422.
CURSOR_SORT = "proposals"


def _to_schema(row, schema: type[ArticleProposalBrief]) -> Any:
    """``(proposal, title, slug, article version)`` row -> ``schema`` with ``article`` and ``is_stale``."""

    proposal, title, slug, version = row
    article = ProposalArticleRef(id=proposal.article_id, title=title, slug=slug)
    is_stale = proposal.status == ArticleProposalStatus.PENDING and proposal.base_version < version
    return schema.model_validate(proposal).model_copy(update={"article": article, "is_stale": is_stale})


def _plain(value: Any) -> Any:
    """JSON-friendly value for a conflict report (enums by value)."""

    return getattr(value, "value", value)


class ArticleProposalsService:
    """``/articles/{id}/proposals`` and the ``/articles/proposals`` queue."""

    def __init__(self, db: AsyncSession):
        """
        Bind to a session. Accepted proposals are written through ``ArticleWriter`` (the same path as a direct
        edit, so history and caches behave identically), which also validates subtypes and reads write state.
        """

        self.db = db
        self.repository = ArticleProposalRepository(db)
        self._revisions = ArticleRevisionRepository(db)
        self._writer = ArticleWriter(db)

    async def propose(
        self, article_id: int, data: ArticleContentUpdate, actor: ArticleActor
    ) -> ArticleProposalResponse:
        """
        Store the article's current content with ``data`` applied, based on its current version.

        Any GM but the article's author (409: they edit directly), the founder included, so they can leave a
        change to the author's judgement.
        """

        state = await self._write_state_or_404(article_id)
        if actor.id == state.author_id:
            raise ArticleProposalNotNeededException(article_id)

        fields = data.model_dump(exclude_unset=True)
        change_note = fields.pop("change_note", None)
        base = await self._revisions.get(article_id, state.version)
        content = {field: fields.get(field, getattr(base, field)) for field in REVISED_FIELDS}
        await self._writer.validate_subtype(content["subtype_id"], content["article_type"])

        async with atomic(self.db):
            proposal_id = await self.repository.create(
                {
                    "article_id": article_id,
                    "base_version": state.version,
                    "proposer_id": actor.id,
                    "change_note": change_note,
                    **content,
                }
            )
        return await self.get_proposal(article_id, proposal_id)

    async def list_proposals(
        self,
        article_id: int,
        statuses: list[ArticleProposalStatus] | None,
        *,
        page: int,
        size: int,
        cursor: str | None = None,
        use_cursor: bool = False,
    ) -> Page[ArticleProposalBrief] | CursorPage[ArticleProposalBrief]:
        """The article's proposals (any of ``statuses``), newest first; 404 if the article doesn't exist."""

        await self._writer.write_state_or_404(article_id)

        return await self._list(
            {"article_id": article_id, "statuses": statuses},
            page=page,
            size=size,
            cursor=cursor,
            use_cursor=use_cursor,
        )

    async def queue(
        self,
        actor: ArticleActor,
        statuses: list[ArticleProposalStatus] | None,
        *,
        mine: bool,
        proposer_id: int | None,
        page: int,
        size: int,
        cursor: str | None = None,
        use_cursor: bool = False,
    ) -> Page[ArticleProposalBrief] | CursorPage[ArticleProposalBrief]:
        """Proposals across all articles: ``mine`` = on articles ``actor`` wrote; ``proposer_id`` = made by that GM."""

        filters = {
            "statuses": statuses,
            "article_author_id": actor.id if mine else None,
            "proposer_id": proposer_id,
        }
        return await self._list(filters, page=page, size=size, cursor=cursor, use_cursor=use_cursor)

    async def get_proposal(self, article_id: int, proposal_id: int) -> ArticleProposalResponse:
        """One full proposal; 404 if the article has no such proposal."""

        return _to_schema(await self._get_or_404(article_id, proposal_id), ArticleProposalResponse)

    async def diff(self, article_id: int, proposal_id: int) -> ArticleRevisionDiff:
        """What the proposal changes relative to the version it was based on (``version`` = the one it would make)."""

        proposal = (await self._get_or_404(article_id, proposal_id))[0]
        base = await self._revisions.get(article_id, proposal.base_version)
        return build_diff(base, proposal, version=proposal.base_version + 1, label=f"proposal-{proposal.id}")

    async def accept(
        self, article_id: int, proposal_id: int, actor: ArticleActor, *, rebase: bool = False
    ) -> ArticleResponse:
        """
        Apply a pending proposal as the next version (editor = proposer, reviewer = ``actor``). Author or founder
        only (the founder may accept their own proposal).

        409 if it is no longer pending, or if the article was edited after the proposal's ``base_version``
        (checked under the article's row lock, so a concurrent edit can't slip in between). With ``rebase`` a
        stale proposal is first merged onto the current version (409 with the conflicts if it can't be); the
        merged content becomes the new version, the stored proposal keeps what was proposed.
        """

        proposal, state = await self._reviewable_or_error(article_id, proposal_id, actor)
        content = {field: getattr(proposal, field) for field in REVISED_FIELDS}
        onto_version = proposal.base_version
        if rebase and state.version != proposal.base_version:
            content = await self._merge_or_conflict(proposal, state.version)
            onto_version = state.version

        async def guard() -> None:
            await self._close(proposal, ArticleProposalStatus.ACCEPTED, actor.id, accepted_version=onto_version + 1)
            current = await self._writer.lock_version(article_id)
            if current is None:
                raise RecordNotFoundError(model_name="Article", model_id=str(article_id))
            if current != onto_version:
                raise ArticleProposalStaleException(proposal_id, onto_version, current)

        return await self._writer.apply_changes(
            article_id,
            content,
            state,
            editor_id=proposal.proposer_id,
            reviewer_id=actor.id,
            change_note=proposal.change_note,
            guard=guard,
        )

    async def rebase(self, article_id: int, proposal_id: int, actor: ArticleActor) -> ArticleProposalResponse:
        """
        Merge a pending proposal onto the article's current version (three-way: its ``base_version`` revision,
        the current revision, the proposal) and store the result with ``base_version`` = current. A no-op for a
        proposal that is already current. 409 with the conflicts (nothing saved) if both sides changed the same
        thing; 409 if it is closed. The proposer, the article's author or the founder only.
        """

        async with atomic(self.db):
            proposal, state = await self._lock_changeable(article_id, proposal_id, actor)
            if proposal.base_version != state.version:
                content = await self._merge_or_conflict(proposal, state.version)
                await self.repository.replace_content(proposal_id, content, base_version=state.version)

        return await self.get_proposal(article_id, proposal_id)

    async def replace(
        self, article_id: int, proposal_id: int, data: ArticleProposalReplace, actor: ArticleActor
    ) -> ArticleProposalResponse:
        """
        Replace a pending proposal's whole content (e.g. a hand-resolved merge conflict). ``data.base_version``
        must be the article's current version (409 otherwise). Same rights as ``rebase``.
        """

        async with atomic(self.db):
            proposal, state = await self._lock_changeable(article_id, proposal_id, actor)
            if data.base_version != state.version:
                raise ArticleProposalStaleException(proposal_id, data.base_version, state.version)

            await self._writer.validate_subtype(data.subtype_id, data.article_type)
            content = data.model_dump(exclude={"base_version"})
            await self.repository.replace_content(proposal_id, content, base_version=data.base_version)

        return await self.get_proposal(article_id, proposal_id)

    async def reject(
        self, article_id: int, proposal_id: int, actor: ArticleActor, reason: str | None = None
    ) -> ArticleProposalResponse:
        """Close a pending proposal without applying it, keeping ``reason``. Author or founder only; 409 if closed."""

        proposal, _ = await self._reviewable_or_error(article_id, proposal_id, actor)

        async with atomic(self.db):
            await self._close(proposal, ArticleProposalStatus.REJECTED, actor.id, review_note=reason)

        return await self.get_proposal(article_id, proposal_id)

    async def withdraw(self, article_id: int, proposal_id: int, actor: ArticleActor) -> ArticleProposalResponse:
        """Take back one's own pending proposal (403 for anyone else, 409 if already closed)."""

        proposal = (await self._get_or_404(article_id, proposal_id))[0]
        if proposal.proposer_id != actor.id:
            raise ArticleProposalWithdrawForbiddenException(proposal_id)

        async with atomic(self.db):
            await self._close(proposal, ArticleProposalStatus.WITHDRAWN, None)

        return await self.get_proposal(article_id, proposal_id)

    async def _lock_changeable(self, article_id: int, proposal_id: int, actor: ArticleActor):
        """
        Lock a pending proposal ``actor`` may change (its proposer, the article's author or the founder) and return
        ``(proposal, article write state)``; 404 / 403 / 409 (closed) otherwise. Call inside ``atomic``.
        """

        proposal = await self.repository.lock(article_id, proposal_id)
        if proposal is None:
            raise RecordNotFoundError(model_name="ArticleProposal", model_id=str(proposal_id))

        state = await self._write_state_or_404(article_id)
        if proposal.proposer_id != actor.id and not actor.can_edit(state.author_id):
            raise ArticleProposalChangeForbiddenException(proposal_id)
        if proposal.status != ArticleProposalStatus.PENDING:
            raise ArticleProposalClosedException(proposal_id, ArticleProposalStatus(proposal.status).value)

        return proposal, state

    async def _merge_or_conflict(self, proposal: ArticleProposal, onto_version: int) -> dict:
        """
        Three-way merge of ``proposal`` onto version ``onto_version``: whole-value for the scalar fields, line-based
        for the body. The merged content, or ``ArticleProposalConflictException`` with every conflict and the body
        merged with conflict markers. The subtype of the merged type is re-validated (400).
        """

        base = await self._revision_or_404(proposal.article_id, proposal.base_version)
        current = await self._revision_or_404(proposal.article_id, onto_version)

        content: dict = {}
        conflicts = []
        for field in DIFF_FIELDS:
            values = getattr(base, field), getattr(current, field), getattr(proposal, field)
            merged = merge_value(*values)
            if merged is CONFLICT:
                base_value, current_value, proposed_value = (_plain(value) for value in values)
                conflicts.append(
                    {"field": field, "base": base_value, "current": current_value, "proposed": proposed_value}
                )
            else:
                content[field] = merged

        body = merge_text(base.body_markdown, current.body_markdown, proposal.body_markdown)
        if conflicts or body.conflicts:
            details = {"conflicts": conflicts, "body_conflicts": body.conflicts, "merged_body": body.text}
            raise ArticleProposalConflictException(proposal.id, details)

        content["body_markdown"] = body.text
        await self._writer.validate_subtype(content["subtype_id"], content["article_type"])
        return content

    async def _reviewable_or_error(self, article_id: int, proposal_id: int, actor: ArticleActor):
        """
        ``(proposal, article write state)`` if ``actor`` may accept/reject it: the author or the founder (403
        otherwise). No separate own-proposal rule: the author can't propose, so the only reviewer who can hold
        their own proposal is the founder, who may decide on it.
        """

        proposal = (await self._get_or_404(article_id, proposal_id))[0]
        state = await self._write_state_or_404(article_id)
        actor.ensure_can_edit(article_id, state.author_id)
        return proposal, state

    async def _list(
        self, filters: dict, *, page: int, size: int, cursor: str | None, use_cursor: bool
    ) -> Page[ArticleProposalBrief] | CursorPage[ArticleProposalBrief]:
        """Shared page/cursor listing behind ``list_proposals`` and ``queue`` (newest first)."""

        if use_cursor:
            before_id = decode_cursor(cursor, CURSOR_SORT).id if cursor is not None else None
            rows, _ = await self.repository.list_proposals(
                **filters, limit=size + 1, before_id=before_id, with_total=False
            )
            rows, next_cursor = cursor_page(rows, size, CURSOR_SORT, lambda row: ("", row[0].id))
            items = [_to_schema(row, ArticleProposalBrief) for row in rows]
            return CursorPage(items=items, next_cursor=next_cursor, size=size)

        skip, limit = paginate(page, size)
        rows, total = await self.repository.list_proposals(**filters, skip=skip, limit=limit)
        items = [_to_schema(row, ArticleProposalBrief) for row in rows]
        return Page(items=items, total=total or 0, page=page, size=size)

    async def _close(
        self,
        proposal: ArticleProposal,
        status: ArticleProposalStatus,
        reviewer_id: int | None,
        *,
        accepted_version: int | None = None,
        review_note: str | None = None,
    ) -> None:
        """Close a pending proposal (conditional UPDATE); 409 with its actual status if it was already closed."""

        closed = await self.repository.close(
            proposal.id, status, reviewer_id=reviewer_id, accepted_version=accepted_version, review_note=review_note
        )
        if not closed:
            await self.db.refresh(proposal)
            raise ArticleProposalClosedException(proposal.id, ArticleProposalStatus(proposal.status).value)

    async def _revision_or_404(self, article_id: int, version: int) -> ArticleRevision:
        """
        One stored revision, or ``RecordNotFoundError``. Every version has a revision, so a miss means the history
        was tampered with; fail loudly instead of merging against nothing.
        """

        revision = await self._revisions.get(article_id, version)
        if revision is None:
            raise RecordNotFoundError(model_name="ArticleRevision", model_id=f"{article_id}@{version}")

        return revision

    async def _write_state_or_404(self, article_id: int):
        """The article's write-state row (author, version, ...), or ``RecordNotFoundError``."""

        return await self._writer.write_state_or_404(article_id)

    async def _get_or_404(self, article_id: int, proposal_id: int):
        """The ``(proposal, title, slug, version)`` row, or ``RecordNotFoundError``."""

        row = await self.repository.get(article_id, proposal_id)
        if row is None:
            raise RecordNotFoundError(model_name="ArticleProposal", model_id=str(proposal_id))

        return row
