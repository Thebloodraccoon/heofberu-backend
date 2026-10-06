"""Unit tests for ``ArticleFilters`` (the listing/search filter value)."""

import dataclasses

import pytest

from app.features.articles.listing.filters import ArticleFilters


class TestArticleFilters:
    @pytest.mark.parametrize("value", [True, False])
    def test_gm_keeps_the_pending_proposals_filter(self, value):
        assert ArticleFilters(include_hidden=True, has_pending_proposals=value).has_pending_proposals is value

    @pytest.mark.parametrize("value", [True, False])
    def test_non_gm_pending_proposals_filter_is_dropped(self, value):
        assert ArticleFilters(include_hidden=False, has_pending_proposals=value).has_pending_proposals is None

    def test_other_filters_are_kept_for_non_gms(self):
        filters = ArticleFilters(include_hidden=False, tag_ids=(3, 7), match_all_tags=True, author_id=5)

        assert (filters.tag_ids, filters.match_all_tags, filters.author_id) == ((3, 7), True, 5)

    def test_is_immutable(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            ArticleFilters(include_hidden=True).include_hidden = False
