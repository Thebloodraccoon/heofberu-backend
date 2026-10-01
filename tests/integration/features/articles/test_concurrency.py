"""
Races on the article write paths, driven through the service layer with one session per task
(the HTTP client shares a single session, so it can't interleave real transactions).
"""

import asyncio

import pytest
from sqlalchemy import select

from app.constants import ArticleStatus
from app.core.exceptions import RecordAlreadyExistsError
from app.features.articles.crud.repository import SLUG_ATTEMPTS, ArticleRepository
from app.features.articles.crud.schemas import ArticleCreate, ArticleUpdate
from app.features.articles.crud.service import ArticleCrudService
from app.features.articles.exceptions import ArticleParentCycleException, ArticleStatusTransitionException
from app.models.articles.article_model import Article
from app.settings import settings


async def _in_own_session(operation):
    """Run ``operation(service)`` with a service on its own session/connection."""

    session = settings.SessionLocal()
    try:
        return await operation(ArticleCrudService(session, storage=object()))
    finally:
        await session.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestSlugRace:
    async def test_concurrent_creates_with_the_same_title_all_get_distinct_slugs(self, db_session):
        async def create(service):
            return await service.create_article(ArticleCreate(title="Moria", article_type="location"))

        results = await asyncio.gather(*(_in_own_session(create) for _ in range(5)))

        assert sorted(r.slug for r in results) == ["moria", "moria-2", "moria-3", "moria-4", "moria-5"]

    async def test_lost_slug_race_is_retried_with_a_fresh_slug(self, client, create_article, db_session, monkeypatch):
        await create_article(title="Moria")
        repo = ArticleRepository(db_session)
        real = repo.generate_unique_slug
        offered = []

        async def stale_first(title, *, exclude_id=None):
            offered.append("moria" if not offered else await real(title, exclude_id=exclude_id))
            return offered[-1]

        monkeypatch.setattr(repo, "generate_unique_slug", stale_first)

        async def write(slug):
            row = Article(title="Moria", slug=slug, article_type="location", body_markdown="")
            db_session.add(row)
            await db_session.flush()
            return row

        row = await repo.write_with_unique_slug("Moria", write)
        await db_session.commit()

        assert offered == ["moria", "moria-2"]
        assert row.slug == "moria-2"

    async def test_gives_up_after_the_attempt_limit(self, client, create_article, db_session, monkeypatch):
        await create_article(title="Moria")
        repo = ArticleRepository(db_session)
        calls = []

        async def always_taken(title, *, exclude_id=None):
            calls.append(1)
            return "moria"

        monkeypatch.setattr(repo, "generate_unique_slug", always_taken)

        async def write(slug):
            db_session.add(Article(title="Moria", slug=slug, article_type="location", body_markdown=""))
            await db_session.flush()

        with pytest.raises(RecordAlreadyExistsError):
            await repo.write_with_unique_slug("Moria", write)

        assert len(calls) == SLUG_ATTEMPTS
        await db_session.rollback()

    async def test_a_failed_attempt_does_not_poison_the_surrounding_transaction(
        self, client, create_article, db_session, monkeypatch
    ):
        await create_article(title="Moria")
        repo = ArticleRepository(db_session)
        offered = iter(["moria"])
        real = repo.generate_unique_slug

        async def stale_once(title, *, exclude_id=None):
            return next(offered, None) or await real(title, exclude_id=exclude_id)

        monkeypatch.setattr(repo, "generate_unique_slug", stale_once)

        async def write(slug):
            db_session.add(Article(title="Moria", slug=slug, article_type="location", body_markdown=""))
            await db_session.flush()

        await repo.write_with_unique_slug("Moria", write)
        await db_session.commit()

        slugs = (await db_session.execute(select(Article.slug).order_by(Article.slug))).scalars().all()
        assert slugs == ["moria", "moria-2"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestParentChangeRace:
    async def test_two_concurrent_moves_cannot_form_a_cycle(self, client, create_article, db_session):
        a = await create_article(title="A")
        b = await create_article(title="B")

        async def move_a_under_b(service):
            return await service.update_article(a["id"], ArticleUpdate(parent_id=b["id"]))

        async def move_b_under_a(service):
            return await service.update_article(b["id"], ArticleUpdate(parent_id=a["id"]))

        results = await asyncio.gather(
            _in_own_session(move_a_under_b), _in_own_session(move_b_under_a), return_exceptions=True
        )

        failures = [r for r in results if isinstance(r, ArticleParentCycleException)]
        assert len(failures) == 1
        assert len([r for r in results if not isinstance(r, Exception)]) == 1
        parents = dict((await db_session.execute(select(Article.id, Article.parent_id))).all())
        assert None in (parents[a["id"]], parents[b["id"]])


@pytest.mark.integration
@pytest.mark.asyncio
class TestTransitionRace:
    async def test_only_one_of_two_concurrent_publishes_wins(self, client, create_article, db_session):
        article = await create_article(status="in_review")

        async def publish(service):
            return await service.transition(article["id"], "publish", actor_id=1)

        results = await asyncio.gather(_in_own_session(publish), _in_own_session(publish), return_exceptions=True)

        assert len([r for r in results if isinstance(r, ArticleStatusTransitionException)]) == 1
        assert len([r for r in results if not isinstance(r, Exception)]) == 1

    async def test_transition_moves_only_from_an_allowed_status(self, client, create_article, db_session):
        article = await create_article(status="published")
        repo = ArticleRepository(db_session)

        moved = await repo.transition_status(
            article["id"], frozenset({ArticleStatus.IN_REVIEW}), ArticleStatus.PUBLISHED, reviewer_id=None
        )
        archived = await repo.transition_status(
            article["id"], frozenset({ArticleStatus.PUBLISHED}), ArticleStatus.ARCHIVED, reviewer_id=None
        )
        await db_session.commit()

        assert (moved, archived) == (False, True)

    async def test_missing_article_is_a_404_not_a_409(self, client, founder_token):
        response = await client.post("/articles/999999/archive", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 404
