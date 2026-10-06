"""Tests for git-style article history (editor/reviewer/hash) and proposed changes (propose, diff, accept, reject)."""

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.constants import UserRole
from app.features.articles.revisions.hashing import revision_hash
from app.models.user_model import User


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_gm(create_user):
    """A second GM, who did not write the articles the tests create."""

    return await create_user(role=UserRole.GM)


@pytest_asyncio.fixture
async def other_gm_token(other_gm, login_as):
    return await login_as(other_gm)


async def _history(client, article_id, token) -> list[dict]:
    response = await client.get(f"/articles/{article_id}/revisions", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _propose(client, article_id, token, **fields):
    return await client.post(f"/articles/{article_id}/proposals", json=fields, headers=_auth(token))


async def _get_proposal(client, article_id, proposal_id, token):
    return await client.get(f"/articles/{article_id}/proposals/{proposal_id}", headers=_auth(token))


async def _review(client, article_id, proposal_id, action, token):
    return await client.post(f"/articles/{article_id}/proposals/{proposal_id}/{action}", headers=_auth(token))


@pytest.mark.integration
@pytest.mark.asyncio
class TestRevisionReviewAndHash:
    async def test_direct_edits_are_self_reviewed(self, client, create_article, gm_token, founder_token, gm, founder):
        article = await create_article()
        await client.patch(f"/articles/{article['id']}", json={"title": "By founder"}, headers=_auth(founder_token))

        history = await _history(client, article["id"], gm_token)

        assert [(r["editor_id"], r["reviewer_id"]) for r in history] == [(founder.id, founder.id), (gm.id, gm.id)]

    async def test_hashes_chain_to_previous_version(self, client, create_article, gm_token):
        article = await create_article(title="Moria", body_markdown="v1")
        await client.patch(f"/articles/{article['id']}", json={"body_markdown": "v2"}, headers=_auth(gm_token))

        v2, v1 = await _history(client, article["id"], gm_token)

        snapshot = (await client.get(f"/articles/{article['id']}/revisions/2", headers=_auth(gm_token))).json()
        fields = ("title", "excerpt", "body_markdown", "article_type", "subtype_id", "visibility")
        content = {field: snapshot[field] for field in fields}
        assert v2["content_hash"] == revision_hash(v1["content_hash"], 2, content)
        assert v1["content_hash"] != v2["content_hash"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestProposals:
    async def test_other_gm_proposes_on_published_article(self, client, create_article, other_gm_token, other_gm):
        article = await create_article(status="published", title="Moria", body_markdown="old")

        response = await _propose(client, article["id"], other_gm_token, body_markdown="new", change_note="typo")

        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["status"], body["base_version"], body["proposer_id"]) == ("pending", 1, other_gm.id)
        assert (body["title"], body["body_markdown"], body["change_note"]) == ("Moria", "new", "typo")

    async def test_author_cannot_propose(self, client, create_article, gm_token):
        article = await create_article()

        assert (await _propose(client, article["id"], gm_token, title="x")).status_code == 409

    async def test_founder_proposes_to_another_authors_article_but_not_their_own(
        self, client, create_article, founder_token, founder
    ):
        article = await create_article()
        own = await client.post(
            "/articles", json={"title": "Founder's", "article_type": "lore"}, headers=_auth(founder_token)
        )

        proposed = await _propose(client, article["id"], founder_token, title="Better title")

        assert proposed.status_code == 201, proposed.text
        assert proposed.json()["proposer_id"] == founder.id
        assert (await _propose(client, own.json()["id"], founder_token, title="x")).status_code == 409

    async def test_anyone_but_the_author_proposes_on_an_authorless_article(
        self, client, create_article, founder_token, other_gm_token, gm, db_session
    ):
        article = await create_article()
        await db_session.execute(delete(User).where(User.id == gm.id))
        await db_session.commit()

        assert (await _propose(client, article["id"], founder_token, title="x")).status_code == 201
        assert (await _propose(client, article["id"], other_gm_token, title="y")).status_code == 201

    async def test_founder_decides_on_their_own_proposal(self, client, create_article, founder_token, founder):
        article = await create_article()
        rejected = (await _propose(client, article["id"], founder_token, title="Second thoughts")).json()
        accepted = (await _propose(client, article["id"], founder_token, title="Founder's idea")).json()

        reject = await _review(client, article["id"], rejected["id"], "reject", founder_token)
        accept = await _review(client, article["id"], accepted["id"], "accept", founder_token)

        assert (reject.status_code, reject.json()["reviewer_id"]) == (200, founder.id)
        assert (accept.status_code, accept.json()["title"]) == (200, "Founder's idea")

    async def test_gm_proposer_cannot_decide_on_their_own_proposal(self, client, create_article, other_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Mine")).json()

        assert (await _review(client, article["id"], proposal["id"], "accept", other_gm_token)).status_code == 403
        assert (await _review(client, article["id"], proposal["id"], "reject", other_gm_token)).status_code == 403

    async def test_player_cannot_propose(self, client, create_article, player_token):
        article = await create_article(status="published")

        assert (await _propose(client, article["id"], player_token, title="x")).status_code == 403

    async def test_diff_against_base_version(self, client, create_article, gm_token, other_gm_token):
        article = await create_article(body_markdown="line one")
        proposal = (await _propose(client, article["id"], other_gm_token, body_markdown="line 1")).json()

        url = f"/articles/{article['id']}/proposals/{proposal['id']}/diff"

        response = await client.get(url, headers=_auth(gm_token))

        body = response.json()
        assert (body["version"], body["against"]) == (2, 1)
        assert "-line one" in body["body_diff"] and "+line 1" in body["body_diff"]

    async def test_accept_creates_version_with_proposer_and_reviewer(
        self, client, create_article, gm_token, other_gm_token, gm, other_gm
    ):
        article = await create_article(status="published", body_markdown="old")
        proposal = (
            await _propose(client, article["id"], other_gm_token, body_markdown="new", change_note="fix")
        ).json()

        response = await _review(client, article["id"], proposal["id"], "accept", gm_token)

        assert response.status_code == 200, response.text
        assert (response.json()["body_markdown"], response.json()["version"]) == ("new", 2)
        assert response.json()["status"] == "published"
        latest = (await _history(client, article["id"], gm_token))[0]
        assert (latest["editor_id"], latest["reviewer_id"], latest["change_note"]) == (other_gm.id, gm.id, "fix")
        closed = (await _get_proposal(client, article["id"], proposal["id"], gm_token)).json()
        assert (closed["status"], closed["reviewer_id"], closed["accepted_version"]) == ("accepted", gm.id, 2)

    async def test_founder_can_accept(self, client, create_article, founder_token, other_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Renamed")).json()

        response = await _review(client, article["id"], proposal["id"], "accept", founder_token)

        assert response.status_code == 200

    async def test_other_gm_cannot_review(self, client, create_article, other_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Mine now")).json()

        assert (await _review(client, article["id"], proposal["id"], "accept", other_gm_token)).status_code == 403
        assert (await _review(client, article["id"], proposal["id"], "reject", other_gm_token)).status_code == 403

    async def test_stale_proposal_cannot_be_accepted(self, client, create_article, gm_token, other_gm_token):
        article = await create_article(body_markdown="v1")
        proposal = (await _propose(client, article["id"], other_gm_token, body_markdown="theirs")).json()
        await client.patch(f"/articles/{article['id']}", json={"body_markdown": "v2"}, headers=_auth(gm_token))

        response = await _review(client, article["id"], proposal["id"], "accept", gm_token)

        assert response.status_code == 409
        still = (await _get_proposal(client, article["id"], proposal["id"], gm_token)).json()
        assert still["status"] == "pending"
        assert len(await _history(client, article["id"], gm_token)) == 2

    async def test_reject_then_cannot_accept(self, client, create_article, gm_token, other_gm_token, gm):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Nope")).json()

        rejected = await _review(client, article["id"], proposal["id"], "reject", gm_token)

        assert rejected.status_code == 200
        assert (rejected.json()["status"], rejected.json()["reviewer_id"]) == ("rejected", gm.id)
        assert (await _review(client, article["id"], proposal["id"], "accept", gm_token)).status_code == 409
        assert len(await _history(client, article["id"], gm_token)) == 1

    async def test_list_filters_by_status(self, client, create_article, gm_token, other_gm_token):
        article = await create_article()
        first = (await _propose(client, article["id"], other_gm_token, title="A")).json()
        await _propose(client, article["id"], other_gm_token, title="B")
        await _review(client, article["id"], first["id"], "reject", gm_token)

        url = f"/articles/{article['id']}/proposals"
        pending = (await client.get(url, params={"status": "pending"}, headers=_auth(gm_token))).json()
        everything = (await client.get(url, headers=_auth(gm_token))).json()

        assert [p["title"] for p in pending["items"]] == ["B"]
        assert everything["total"] == 2

    async def test_missing_proposal_is_404(self, client, create_article, gm_token):
        article = await create_article()

        response = await client.get(f"/articles/{article['id']}/proposals/999999", headers=_auth(gm_token))

        assert response.status_code == 404

    async def test_list_articles_with_pending_proposals(self, client, create_article, gm_token, other_gm_token):
        waiting = await create_article(title="Waiting")
        reviewed = await create_article(title="Reviewed")
        await create_article(title="Untouched")
        await _propose(client, waiting["id"], other_gm_token, body_markdown="please")
        done = (await _propose(client, reviewed["id"], other_gm_token, body_markdown="nope")).json()
        await _review(client, reviewed["id"], done["id"], "reject", gm_token)

        response = await client.get("/articles", params={"has_pending_proposals": "true"}, headers=_auth(gm_token))

        assert response.status_code == 200
        assert [a["id"] for a in response.json()["items"]] == [waiting["id"]]

    async def test_pending_proposals_filter_is_ignored_for_non_gm(self, client, create_article, other_gm_token):
        article = await create_article(status="published")

        response = await client.get("/articles", params={"has_pending_proposals": "true"})

        assert [a["id"] for a in response.json()["items"]] == [article["id"]]


@pytest.mark.integration
@pytest.mark.asyncio
class TestProposalCountsAndSearch:
    async def test_pending_count_is_shown_to_gm_only(self, client, create_article, gm_token, other_gm_token):
        article = await create_article(title="Moria", status="published")
        await _propose(client, article["id"], other_gm_token, body_markdown="a")
        await _propose(client, article["id"], other_gm_token, body_markdown="b")

        gm_rows = (await client.get("/articles", headers=_auth(gm_token))).json()["items"]
        public_rows = (await client.get("/articles")).json()["items"]
        gm_hits = (await client.get("/articles/search", params={"q": "moria"}, headers=_auth(gm_token))).json()

        assert [r["pending_proposals"] for r in gm_rows] == [2]
        assert [r["pending_proposals"] for r in public_rows] == [None]
        assert [r["pending_proposals"] for r in gm_hits["items"]] == [2]

    async def test_search_filters_by_status_and_pending_proposals(
        self, client, create_article, gm_token, other_gm_token
    ):
        waiting = await create_article(title="Moria Gate", status="published")
        await create_article(title="Moria Halls")
        await _propose(client, waiting["id"], other_gm_token, body_markdown="please")

        def search(**params):
            return client.get("/articles/search", params={"q": "moria", **params}, headers=_auth(gm_token))

        pending = (await search(has_pending_proposals="true")).json()["items"]
        drafts = (await search(status="draft")).json()["items"]

        assert [i["title"] for i in pending] == ["Moria Gate"]
        assert [i["title"] for i in drafts] == ["Moria Halls"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestProposalQueueAndLifecycle:
    async def test_several_statuses_at_once(self, client, create_article, gm_token, other_gm_token):
        article = await create_article()
        ids = [(await _propose(client, article["id"], other_gm_token, title=t)).json()["id"] for t in "ABC"]
        await _review(client, article["id"], ids[0], "reject", gm_token)
        await _review(client, article["id"], ids[1], "accept", gm_token)

        response = await client.get(
            f"/articles/{article['id']}/proposals",
            params={"status": ["accepted", "rejected"]},
            headers=_auth(gm_token),
        )

        assert sorted(p["title"] for p in response.json()["items"]) == ["A", "B"]

    async def test_queue_mine_lists_proposals_on_my_articles_with_article_ref(
        self, client, create_article, gm_token, founder_token, other_gm_token, other_gm
    ):
        mine = await create_article(title="Mine")
        theirs = await client.post(
            "/articles", json={"title": "Founder's", "article_type": "lore"}, headers=_auth(founder_token)
        )
        await _propose(client, mine["id"], other_gm_token, body_markdown="x")
        await _propose(client, theirs.json()["id"], other_gm_token, body_markdown="y")

        queue = await client.get(
            "/articles/proposals", params={"status": "pending", "mine": "true"}, headers=_auth(gm_token)
        )
        by_proposer = await client.get(
            "/articles/proposals", params={"proposer_id": other_gm.id}, headers=_auth(gm_token)
        )

        assert queue.status_code == 200, queue.text
        assert [p["article"] for p in queue.json()["items"]] == [
            {"id": mine["id"], "title": "Mine", "slug": mine["slug"]}
        ]
        assert by_proposer.json()["total"] == 2

    async def test_queue_is_gm_only(self, client, player_token):
        assert (await client.get("/articles/proposals", headers=_auth(player_token))).status_code == 403

    async def test_reject_with_reason(self, client, create_article, gm_token, other_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Nope")).json()

        response = await client.post(
            f"/articles/{article['id']}/proposals/{proposal['id']}/reject",
            json={"reason": "Contradicts the canon"},
            headers=_auth(gm_token),
        )

        assert (response.json()["status"], response.json()["review_note"]) == ("rejected", "Contradicts the canon")

    async def test_proposer_withdraws_and_it_can_no_longer_be_accepted(
        self, client, create_article, gm_token, other_gm_token
    ):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Oops")).json()

        withdrawn = await _review(client, article["id"], proposal["id"], "withdraw", other_gm_token)

        assert withdrawn.status_code == 200, withdrawn.text
        assert (withdrawn.json()["status"], withdrawn.json()["reviewer_id"]) == ("withdrawn", None)
        assert (await _review(client, article["id"], proposal["id"], "accept", gm_token)).status_code == 409
        assert (await _review(client, article["id"], proposal["id"], "withdraw", other_gm_token)).status_code == 409

    async def test_only_the_proposer_can_withdraw(self, client, create_article, gm_token, other_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="Mine")).json()

        response = await _review(client, article["id"], proposal["id"], "withdraw", gm_token)

        assert response.status_code == 403

    async def test_cursor_pagination(self, client, create_article, gm_token, other_gm_token):
        article = await create_article()
        for title in "ABC":
            await _propose(client, article["id"], other_gm_token, title=title)
        url = f"/articles/{article['id']}/proposals"

        headers = _auth(gm_token)

        first = (await client.get(url, params={"pagination": "cursor", "size": 2}, headers=headers)).json()
        second = (await client.get(url, params={"cursor": first["next_cursor"], "size": 2}, headers=headers)).json()

        assert [p["title"] for p in first["items"]] == ["C", "B"]
        assert ([p["title"] for p in second["items"]], second["next_cursor"]) == (["A"], None)


@pytest_asyncio.fixture
async def third_gm_token(create_user, login_as):
    """A GM who is neither the author nor the proposer."""

    return await login_as(await create_user(role=UserRole.GM))


async def _stale_pair(client, create_article, gm_token, other_gm_token, first: dict, second: dict, **article):
    """Two proposals on version 1; the author accepts the first, so the second is left on a stale base."""

    created = await create_article(**article)
    one = (await _propose(client, created["id"], other_gm_token, **first)).json()
    two = (await _propose(client, created["id"], other_gm_token, **second)).json()
    accepted = await _review(client, created["id"], one["id"], "accept", gm_token)
    assert accepted.status_code == 200, accepted.text
    return created, two


@pytest.mark.integration
@pytest.mark.asyncio
class TestRebase:
    BODY = "line one\nline two\nline three\n"

    async def test_rebase_without_conflict_then_accept(
        self, client, create_article, gm_token, other_gm_token, gm, other_gm
    ):
        article, proposal = await _stale_pair(
            client,
            create_article,
            gm_token,
            other_gm_token,
            {"body_markdown": "line two\nline three\n"},
            {"body_markdown": "line one\nline two\nline 3\n", "title": "Renamed"},
            body_markdown=self.BODY,
        )
        stale = (await _get_proposal(client, article["id"], proposal["id"], gm_token)).json()

        rebased = await _review(client, article["id"], proposal["id"], "rebase", other_gm_token)

        assert stale["is_stale"] is True
        assert rebased.status_code == 200, rebased.text
        body = rebased.json()
        assert (body["base_version"], body["is_stale"]) == (2, False)
        assert (body["title"], body["body_markdown"]) == ("Renamed", "line two\nline 3\n")
        accepted = await _review(client, article["id"], proposal["id"], "accept", gm_token)
        assert accepted.status_code == 200, accepted.text
        latest = (await _history(client, article["id"], gm_token))[0]
        assert (latest["version"], latest["editor_id"], latest["reviewer_id"]) == (3, other_gm.id, gm.id)

    async def test_conflict_in_one_line_saves_nothing(self, client, create_article, gm_token, other_gm_token):
        article, proposal = await _stale_pair(
            client,
            create_article,
            gm_token,
            other_gm_token,
            {"body_markdown": "line one\nline A\nline three\n"},
            {"body_markdown": "line one\nline B\nline three\n"},
            body_markdown=self.BODY,
        )

        response = await _review(client, article["id"], proposal["id"], "rebase", gm_token)

        assert response.status_code == 409
        details = response.json()["error"]["details"]
        assert details["conflicts"] == []
        assert details["body_conflicts"] == [{"base": "line two\n", "current": "line A\n", "proposed": "line B\n"}]
        assert "<<<<<<< current\nline A\n" in details["merged_body"]
        unchanged = (await _get_proposal(client, article["id"], proposal["id"], gm_token)).json()
        assert (unchanged["base_version"], unchanged["body_markdown"]) == (1, "line one\nline B\nline three\n")

    async def test_conflict_in_title(self, client, create_article, gm_token, other_gm_token):
        article, proposal = await _stale_pair(
            client,
            create_article,
            gm_token,
            other_gm_token,
            {"title": "Khazad-dum"},
            {"title": "Dwarrowdelf"},
            title="Moria",
        )

        response = await _review(client, article["id"], proposal["id"], "rebase", gm_token)

        assert response.status_code == 409
        assert response.json()["error"]["details"]["conflicts"] == [
            {"field": "title", "base": "Moria", "current": "Khazad-dum", "proposed": "Dwarrowdelf"}
        ]

    async def test_rebase_of_a_closed_proposal_is_409(self, client, create_article, gm_token, other_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="x")).json()
        await _review(client, article["id"], proposal["id"], "reject", gm_token)

        assert (await _review(client, article["id"], proposal["id"], "rebase", other_gm_token)).status_code == 409

    async def test_another_gm_cannot_rebase_or_replace(self, client, create_article, other_gm_token, third_gm_token):
        article = await create_article()
        proposal = (await _propose(client, article["id"], other_gm_token, title="x")).json()
        replacement = {"base_version": 1, "title": "y", "article_type": article["article_type"]}
        url = f"/articles/{article['id']}/proposals/{proposal['id']}"

        rebase = await _review(client, article["id"], proposal["id"], "rebase", third_gm_token)
        replace = await client.put(url, json=replacement, headers=_auth(third_gm_token))

        assert (rebase.status_code, replace.status_code) == (403, 403)

    async def test_resolve_conflict_by_hand_with_put(self, client, create_article, gm_token, other_gm_token):
        article, proposal = await _stale_pair(
            client,
            create_article,
            gm_token,
            other_gm_token,
            {"title": "Khazad-dum"},
            {"title": "Dwarrowdelf"},
            title="Moria",
        )
        url = f"/articles/{article['id']}/proposals/{proposal['id']}"
        resolved = {"title": "Khazad-dum (Dwarrowdelf)", "article_type": article["article_type"]}

        stale = await client.put(url, json={**resolved, "base_version": 1}, headers=_auth(other_gm_token))
        saved = await client.put(url, json={**resolved, "base_version": 2}, headers=_auth(other_gm_token))

        assert stale.status_code == 409
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert (body["title"], body["base_version"], body["is_stale"]) == ("Khazad-dum (Dwarrowdelf)", 2, False)
        assert (await _review(client, article["id"], proposal["id"], "accept", gm_token)).status_code == 200

    async def test_accept_with_rebase(self, client, create_article, gm_token, other_gm_token):
        article, proposal = await _stale_pair(
            client,
            create_article,
            gm_token,
            other_gm_token,
            {"body_markdown": "line ONE\nline two\nline three\n"},
            {"body_markdown": "line one\nline two\nline THREE\n"},
            body_markdown=self.BODY,
        )
        url = f"/articles/{article['id']}/proposals/{proposal['id']}/accept"

        plain = await client.post(url, headers=_auth(gm_token))
        rebased = await client.post(url, params={"rebase": "true"}, headers=_auth(gm_token))

        assert plain.status_code == 409
        assert rebased.status_code == 200, rebased.text
        body = rebased.json()
        assert (body["body_markdown"], body["version"]) == ("line ONE\nline two\nline THREE\n", 3)

    async def test_accept_with_rebase_reports_conflicts(self, client, create_article, gm_token, other_gm_token):
        article, proposal = await _stale_pair(
            client,
            create_article,
            gm_token,
            other_gm_token,
            {"title": "Khazad-dum"},
            {"title": "Dwarrowdelf"},
            title="Moria",
        )
        url = f"/articles/{article['id']}/proposals/{proposal['id']}/accept"

        response = await client.post(url, params={"rebase": "true"}, headers=_auth(gm_token))

        assert response.status_code == 409
        assert response.json()["error"]["details"]["conflicts"][0]["field"] == "title"
        assert len(await _history(client, article["id"], gm_token)) == 2
