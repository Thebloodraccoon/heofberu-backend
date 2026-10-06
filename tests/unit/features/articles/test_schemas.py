"""Unit tests for the article/relation request schemas (input bounds and GM-block rules)."""

from pydantic import ValidationError
import pytest

from app.features.articles.crud.schemas import BODY_MAX_LENGTH, ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.relations.schemas import NOTE_MAX_LENGTH, ArticleRelationCreate, ArticleRelationUpdate

NESTED = ":::gm\nsecret\n:::spoiler\nx\n:::\nmore secret\n:::"


class TestArticleCreate:
    def test_title_is_trimmed_and_collapsed(self):
        article = ArticleCreate(title="  Khazad   dum \n", article_type="location")

        assert article.title == "Khazad dum"

    @pytest.mark.parametrize("title", ["", "   ", "\n\t"])
    def test_blank_title_is_rejected(self, title):
        with pytest.raises(ValidationError):
            ArticleCreate(title=title, article_type="location")

    def test_title_longer_than_200_is_rejected(self):
        with pytest.raises(ValidationError):
            ArticleCreate(title="x" * 201, article_type="location")

    def test_unknown_article_type_is_rejected(self):
        with pytest.raises(ValidationError):
            ArticleCreate(title="x", article_type="not_a_real_type")

    @pytest.mark.parametrize("field", ["body_markdown", "excerpt"])
    def test_nested_container_in_gm_block_is_rejected(self, field):
        with pytest.raises(ValidationError, match="must not contain another"):
            ArticleCreate(title="x", article_type="location", **{field: NESTED})

    def test_flat_gm_block_and_other_containers_are_accepted(self):
        body = ":::note\nhi\n:::\n:::gm\nsecret\n:::"

        assert ArticleCreate(title="x", article_type="location", body_markdown=body).body_markdown == body

    def test_body_over_the_limit_is_rejected(self):
        with pytest.raises(ValidationError):
            ArticleCreate(title="x", article_type="location", body_markdown="a" * (BODY_MAX_LENGTH + 1))


class TestArticleUpdate:
    def test_only_provided_fields_are_set(self):
        assert ArticleUpdate(title=" New ").model_dump(exclude_unset=True) == {"title": "New"}

    @pytest.mark.parametrize("field", ["title", "body_markdown", "article_type", "visibility"])
    def test_explicit_null_is_rejected_for_not_null_columns(self, field):
        with pytest.raises(ValidationError):
            ArticleUpdate(**{field: None})

    def test_excerpt_may_be_cleared(self):
        assert ArticleUpdate(excerpt=None).model_dump(exclude_unset=True) == {"excerpt": None}

    def test_nested_container_in_gm_block_is_rejected(self):
        with pytest.raises(ValidationError):
            ArticleUpdate(body_markdown=NESTED)

    def test_blank_title_is_rejected(self):
        with pytest.raises(ValidationError):
            ArticleUpdate(title="  ")


class TestArticleResponse:
    def test_legacy_row_with_blank_title_and_nested_block_still_serializes(self):
        """Write rules must not make already-stored rows unreadable."""

        response = ArticleResponse.model_validate(
            {
                "id": 1,
                "slug": "x",
                "title": " ",
                "body_markdown": NESTED,
                "article_type": "legacy_type",
                "status": "draft",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

        assert response.article_type == "legacy_type"


class TestRelationNote:
    def test_note_at_the_column_limit_is_accepted(self):
        data = ArticleRelationCreate(to_article_id=2, relation_type="MENTIONS", note="n" * NOTE_MAX_LENGTH)

        assert len(data.note) == NOTE_MAX_LENGTH

    @pytest.mark.parametrize("schema", [ArticleRelationCreate, ArticleRelationUpdate])
    def test_note_over_300_is_rejected(self, schema):
        extra = {"to_article_id": 2, "relation_type": "MENTIONS"} if schema is ArticleRelationCreate else {}

        with pytest.raises(ValidationError):
            schema(note="n" * (NOTE_MAX_LENGTH + 1), **extra)

    def test_nested_container_in_gm_block_is_rejected(self):
        with pytest.raises(ValidationError):
            ArticleRelationUpdate(note=NESTED)

    def test_note_may_be_cleared_on_update(self):
        assert ArticleRelationUpdate(note=None).model_dump(exclude_unset=True) == {"note": None}
