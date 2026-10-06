"""Unit tests for article slug generation."""

import pytest

from app.features.articles.slug import FALLBACK_SLUG, SLUG_MAX_LENGTH, slugify


class TestSlugify:
    @pytest.mark.parametrize(
        ("title", "slug"),
        [
            ("Khazad-dum", "khazad-dum"),
            ("Хазад-дум", "khazad-dum"),
            ("Аурис, бог Солнца", "auris-bog-solntsa"),
            ("  Many   spaces & symbols!  ", "many-spaces-symbols"),
            ("Щука Ёжик", "shchuka-yozhik"),
        ],
    )
    def test_titles_become_ascii_slugs(self, title, slug):
        assert slugify(title) == slug

    @pytest.mark.parametrize("title", ["", "   ", "!!!", "—", "ъь"])
    def test_nothing_usable_falls_back(self, title):
        assert slugify(title) == FALLBACK_SLUG

    def test_long_title_is_cut_without_trailing_dash(self):
        slug = slugify("word " * 100)

        assert len(slug) <= SLUG_MAX_LENGTH
        assert not slug.endswith("-")
