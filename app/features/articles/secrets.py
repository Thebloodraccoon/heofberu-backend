"""
GM-only blocks inside article text: ``:::gm`` ... ``:::``, stripped for non-GM readers.

Markdown containers nest (``:::spoiler`` inside ``:::gm``), and every ``:::`` closes only
the innermost one, so a flat "up to the first ``:::``" match would close a GM block early and
show the rest of it. ``strip_gm_blocks`` therefore tracks container depth; an unclosed block
runs to the end of the text (fail closed).

The database side (generated ``search_vector`` and the SQL used for excerpts/snippets) can only do
a flat match, so two guards keep it equivalent: article text is rejected on write when a GM block
contains another container (``has_nested_gm_container``), and ``gm_stripped_sql`` first removes any
such block, from its opening to the end of the text, before applying the flat pattern.
"""

import re

from sqlalchemy import func

from app.constants import ARTICLE_GM_BLOCK_SQL_PATTERN

#: Every position where ``:::`` starts, with the container name after it (``:::gm``, ``:::note``; a bare
#: ``:::`` closes). Zero-width, so overlapping runs of colons (``::::gm``) are all inspected.
_CONTAINER_TOKEN = re.compile(r"(?=:::([A-Za-z][\w-]*)?)")

#: Postgres twin for a GM block that contains another container: from ``:::gm`` to the end of the text.
NESTED_GM_BLOCK_SQL_PATTERN = r"(?i):::gm(?:(?!:::).)*:::[a-z].*"


def _scan(text: str) -> tuple[str, bool]:
    """Return ``(text without GM blocks, whether a GM block contained another container)``."""

    visible: list[str] = []
    position = depth = skip_until = 0
    nested = False

    for token in _CONTAINER_TOKEN.finditer(text):
        start, name = token.start(), token.group(1)
        if depth and start < skip_until:
            continue

        if depth == 0:
            if name and name.lower().startswith("gm"):
                visible.append(text[position:start])
                depth = 1
                skip_until = start + 3 + len(name)
        elif name:
            depth += 1
            nested = True
            skip_until = start + 3 + len(name)
        else:
            depth -= 1
            skip_until = start + 3
            if depth == 0:
                position = skip_until

    if depth == 0:
        visible.append(text[position:])

    return "".join(visible), nested


def strip_gm_blocks(text: str | None) -> str | None:
    """Return ``text`` (body, excerpt, relation note) with every GM-only block removed; ``None`` stays ``None``."""

    return _scan(text)[0] if text else text


def has_nested_gm_container(text: str | None) -> bool:
    """Whether a GM block in ``text`` contains another ``:::`` container (including another ``:::gm``)."""

    return _scan(text)[1] if text else False


def gm_stripped_sql(column, replacement: str = " "):
    """SQL expression for ``column`` with GM blocks removed (nested blocks fail closed, see the module docstring)."""

    without_nested = func.regexp_replace(column, NESTED_GM_BLOCK_SQL_PATTERN, replacement, "g")
    return func.regexp_replace(without_nested, ARTICLE_GM_BLOCK_SQL_PATTERN, replacement, "g")
