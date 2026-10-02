"""Unit tests for the three-way merge used to rebase article proposals (no DB)."""

import pytest

from app.features.articles.revisions.merge import CONFLICT, merge_text, merge_value

BASE = "one\ntwo\nthree\nfour\n"


@pytest.mark.unit
class TestMergeValue:
    def test_only_the_proposal_changed(self):
        assert merge_value("Moria", "Moria", "Khazad-dum") == "Khazad-dum"

    def test_only_the_current_version_changed(self):
        assert merge_value("Moria", "Khazad-dum", "Moria") == "Khazad-dum"

    def test_same_change_on_both_sides(self):
        assert merge_value("Moria", "Khazad-dum", "Khazad-dum") == "Khazad-dum"

    def test_different_changes_conflict(self):
        assert merge_value("Moria", "Khazad-dum", "Dwarrowdelf") is CONFLICT

    def test_none_is_a_value(self):
        assert merge_value(None, None, "excerpt") == "excerpt"
        assert merge_value("excerpt", "excerpt", None) is None


@pytest.mark.unit
class TestMergeText:
    def test_changes_in_different_lines_are_both_kept(self):
        merged = merge_text(BASE, "one\nTWO\nthree\nfour\n", "one\ntwo\nthree\n")

        assert (merged.text, merged.conflicts) == ("one\nTWO\nthree\n", [])

    def test_identical_change_is_taken_once(self):
        merged = merge_text(BASE, "one\nTWO\nthree\nfour\n", "one\nTWO\nthree\nfour\n")

        assert (merged.text, merged.conflicts) == ("one\nTWO\nthree\nfour\n", [])

    def test_unchanged_sides(self):
        assert merge_text(BASE, BASE, BASE).text == BASE
        assert merge_text(BASE, BASE, "new\n").text == "new\n"
        assert merge_text(BASE, "new\n", BASE).text == "new\n"

    def test_edits_at_both_ends(self):
        merged = merge_text(BASE, "zero\n" + BASE, BASE + "five\n")

        assert (merged.text, merged.conflicts) == ("zero\n" + BASE + "five\n", [])

    def test_different_changes_of_one_line_conflict_with_markers(self):
        merged = merge_text(BASE, "one\nX\nthree\nfour\n", "one\nY\nthree\nfour\n")

        assert merged.conflicts == [{"base": "two\n", "current": "X\n", "proposed": "Y\n"}]
        assert merged.text == (
            "one\n<<<<<<< current\nX\n||||||| base\ntwo\n=======\nY\n>>>>>>> proposal\nthree\nfour\n"
        )

    def test_changes_in_adjacent_lines_conflict_like_git(self):
        merged = merge_text(BASE, "one\nTWO\nthree\nfour\n", "one\ntwo\nTHREE\nfour\n")

        assert len(merged.conflicts) == 1

    def test_delete_against_edit_conflicts(self):
        merged = merge_text(BASE, "one\nthree\nfour\n", "one\nTWO\nthree\nfour\n")

        assert merged.conflicts == [{"base": "two\n", "current": "", "proposed": "TWO\n"}]

    def test_insertions_at_the_same_place_conflict(self):
        merged = merge_text(BASE, "one\nA\ntwo\nthree\nfour\n", "one\nB\ntwo\nthree\nfour\n")

        assert len(merged.conflicts) == 1
        assert (merged.conflicts[0]["current"], merged.conflicts[0]["proposed"]) == ("A\n", "B\n")

    def test_marker_starts_a_line_even_without_a_final_newline(self):
        merged = merge_text("a", "b", "c")

        assert merged.text == "<<<<<<< current\nb\n||||||| base\na\n=======\nc\n>>>>>>> proposal\n"
