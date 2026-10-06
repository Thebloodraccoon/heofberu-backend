"""Unit tests for GM-block stripping (``strip_gm_blocks``) and the nesting guard."""

import pytest

from app.features.articles.secrets import has_nested_gm_container, strip_gm_blocks


class TestStripGmBlocks:
    @pytest.mark.parametrize("empty", [None, ""])
    def test_empty_input_is_returned_unchanged(self, empty):
        assert strip_gm_blocks(empty) == empty

    def test_text_without_blocks_is_unchanged(self):
        assert strip_gm_blocks("A quiet fortress.") == "A quiet fortress."

    def test_block_is_removed_and_surroundings_kept(self):
        text = "Before.\n\n:::gm\nsecret\n:::\n\nAfter."

        assert strip_gm_blocks(text) == "Before.\n\n\n\nAfter."

    def test_inline_block_without_newlines(self):
        assert strip_gm_blocks("A border keep.:::gm Balrogborn sleeps here.:::") == "A border keep."

    @pytest.mark.parametrize("opener", [":::GM", ":::Gm", ":::gM"])
    def test_opener_is_case_insensitive(self, opener):
        assert "secret" not in strip_gm_blocks(f"x\n{opener}\nsecret\n:::\ny")

    def test_several_blocks_are_all_removed(self):
        text = "a :::gm one ::: b :::gm two ::: c"

        assert strip_gm_blocks(text) == "a  b  c"

    def test_unclosed_block_runs_to_the_end(self):
        assert strip_gm_blocks("public\n:::gm\nsecret forever") == "public\n"

    def test_other_containers_outside_gm_blocks_are_kept(self):
        text = ":::note\nvisible\n:::\n:::gm\nsecret\n:::\ntail"

        assert strip_gm_blocks(text) == ":::note\nvisible\n:::\n\ntail"

    def test_nested_container_does_not_close_the_gm_block_early(self):
        text = ":::gm\nsecret\n:::spoiler\nx\n:::\nmore secret\n:::\npublic"

        result = strip_gm_blocks(text)

        assert "secret" not in result
        assert result.endswith("\npublic")

    def test_deeply_nested_containers_are_tracked(self):
        text = ":::gm\na\n:::one\nb\n:::two\nc\n:::\nd\n:::\ne\n:::\npublic"

        assert strip_gm_blocks(text) == "\npublic"

    def test_nested_gm_inside_gm_is_removed_with_the_outer_block(self):
        text = ":::gm\nouter\n:::gm\ninner\n:::\nstill outer\n:::\npublic"

        assert strip_gm_blocks(text) == "\npublic"

    def test_nested_block_left_unclosed_fails_closed(self):
        text = "public\n:::gm\nsecret\n:::spoiler\nx\n:::\nnever closed"

        assert strip_gm_blocks(text) == "public\n"

    def test_four_colon_opener_is_still_found(self):
        assert "secret" not in strip_gm_blocks("public ::::gm secret :::")

    def test_overlong_colon_run_inside_block_closes_only_one_level(self):
        text = ":::gm\nhidden\n:::spoiler\nb\n:::::\nalso hidden\n:::\npublic"

        result = strip_gm_blocks(text)

        assert "hidden" not in result
        assert result.endswith("public")


class TestHasNestedGmContainer:
    @pytest.mark.parametrize("text", [None, "", "plain", ":::gm\nsecret\n:::", ":::note\nx\n:::\n:::gm\ny\n:::"])
    def test_flat_text_is_not_nested(self, text):
        assert not has_nested_gm_container(text)

    @pytest.mark.parametrize(
        "text",
        [
            ":::gm\nsecret\n:::spoiler\nx\n:::\n:::",
            ":::gm\n:::gm\nx\n:::\n:::",
            ":::GM\nx :::note y ::: z\n:::",
        ],
    )
    def test_container_inside_gm_is_nested(self, text):
        assert has_nested_gm_container(text)
