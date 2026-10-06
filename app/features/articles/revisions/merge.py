"""
Three-way merge of article content (like ``git rebase`` of a proposal onto the article's newest version).

``base`` is the version both sides started from, ``current`` the article as it is now, ``proposed`` the proposal.
Pure functions over plain values; stdlib only (``difflib``).
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

#: Sentinel: the field changed differently on both sides.
CONFLICT = object()


def merge_value(base: Any, current: Any, proposed: Any) -> Any:
    """Whole-value merge of one field: the side that changed it wins; both changed differently -> ``CONFLICT``."""

    if proposed == base:
        return current
    if current in (base, proposed):
        return proposed
    return CONFLICT


@dataclass
class TextMerge:
    """Merged text (with ``<<<<<<<`` conflict markers if ``conflicts``) and the conflicting hunks."""

    text: str
    conflicts: list[dict[str, str]] = field(default_factory=list)


def _sync_regions(base: list[str], current: list[str], proposed: list[str]) -> list[tuple[int, int, int, int]]:
    """
    Ranges of ``base`` left untouched on BOTH sides: ``(base_start, base_end, current_start, proposed_start)``,
    ending with an empty sentinel region at the very end of all three texts.
    """

    to_current = SequenceMatcher(None, base, current, autojunk=False).get_matching_blocks()
    to_proposed = SequenceMatcher(None, base, proposed, autojunk=False).get_matching_blocks()
    regions = []
    i = j = 0
    while i < len(to_current) and j < len(to_proposed):
        c_base, c_at, c_len = to_current[i]
        p_base, p_at, p_len = to_proposed[j]
        start, end = max(c_base, p_base), min(c_base + c_len, p_base + p_len)
        if start < end:
            regions.append((start, end, c_at + start - c_base, p_at + start - p_base))
        if c_base + c_len < p_base + p_len:
            i += 1
        else:
            j += 1

    regions.append((len(base), len(base), len(current), len(proposed)))
    return regions


def _terminated(lines: list[str]) -> list[str]:
    """Lines with a final newline, so a conflict marker after them starts on its own line."""

    if lines and not lines[-1].endswith("\n"):
        return [*lines[:-1], lines[-1] + "\n"]
    return lines


def merge_text(base: str, current: str, proposed: str) -> TextMerge:
    """
    Line-based diff3: hunks changed on one side only are applied, hunks changed identically on both are taken
    once, hunks changed differently on both are conflicts (written between ``<<<<<<< current`` /
    ``||||||| base`` / ``=======`` / ``>>>>>>> proposal`` markers into the merged text). As in git, edits of
    adjacent lines with no unchanged line between them form one hunk, so they conflict.
    """

    b, c, p = (text.splitlines(keepends=True) for text in (base, current, proposed))
    merged: list[str] = []
    conflicts: list[dict[str, str]] = []
    b_at = c_at = p_at = 0
    for b_start, b_end, c_start, p_start in _sync_regions(b, c, p):
        b_hunk, c_hunk, p_hunk = b[b_at:b_start], c[c_at:c_start], p[p_at:p_start]
        if c_hunk == b_hunk:
            merged += p_hunk
        elif p_hunk in (b_hunk, c_hunk):
            merged += c_hunk
        else:
            conflicts.append({"base": "".join(b_hunk), "current": "".join(c_hunk), "proposed": "".join(p_hunk)})
            merged += [
                "<<<<<<< current\n",
                *_terminated(c_hunk),
                "||||||| base\n",
                *_terminated(b_hunk),
                "=======\n",
                *_terminated(p_hunk),
                ">>>>>>> proposal\n",
            ]

        length = b_end - b_start
        merged += b[b_start:b_end]
        b_at, c_at, p_at = b_end, c_start + length, p_start + length

    return TextMerge(text="".join(merged), conflicts=conflicts)
