"""Unit tests for the revision diff builder (no DB)."""

from types import SimpleNamespace

import pytest

from app.constants import ArticleVisibility
from app.features.articles.access import ArticleActor
from app.features.articles.exceptions import ArticleEditForbiddenException
from app.features.articles.revisions.service import build_diff


def _revision(version: int, **overrides):
    values = {
        "version": version,
        "title": "Moria",
        "excerpt": None,
        "body_markdown": "a\nb",
        "article_type": "location",
        "subtype_id": None,
        "visibility": ArticleVisibility.PUBLIC,
    }
    return SimpleNamespace(**{**values, **overrides})


@pytest.mark.unit
class TestBuildDiff:
    def test_identical_versions_have_no_changes(self):
        diff = build_diff(_revision(1), _revision(2))

        assert diff.fields == {}
        assert diff.body_diff == ""

    def test_reports_changed_scalar_fields_with_enum_values(self):
        diff = build_diff(_revision(1), _revision(2, title="Khazad-dum", visibility=ArticleVisibility.GM_ONLY))

        assert diff.fields["title"].model_dump() == {"old": "Moria", "new": "Khazad-dum"}
        assert diff.fields["visibility"].model_dump() == {"old": "public", "new": "gm_only"}

    def test_body_diff_is_unified(self):
        diff = build_diff(_revision(1), _revision(2, body_markdown="a\nc"))

        assert "--- v1" in diff.body_diff and "+++ v2" in diff.body_diff
        assert "-b" in diff.body_diff and "+c" in diff.body_diff

    def test_no_previous_version_means_everything_is_added(self):
        diff = build_diff(None, _revision(1))

        assert diff.against == 0
        assert "+a" in diff.body_diff and "+b" in diff.body_diff


@pytest.mark.unit
class TestArticleActor:
    def test_author_may_edit(self):
        ArticleActor(id=5, is_founder=False).ensure_can_edit(1, author_id=5)

    def test_founder_may_edit_anything(self):
        ArticleActor(id=1, is_founder=True).ensure_can_edit(1, author_id=5)
        ArticleActor(id=1, is_founder=True).ensure_can_edit(1, author_id=None)

    def test_other_gm_may_not(self):
        with pytest.raises(ArticleEditForbiddenException):
            ArticleActor(id=6, is_founder=False).ensure_can_edit(1, author_id=5)

    def test_gm_may_not_edit_authorless_article(self):
        with pytest.raises(ArticleEditForbiddenException):
            ArticleActor(id=6, is_founder=False).ensure_can_edit(1, author_id=None)
