"""GM-only blocks inside an article body: ``:::gm`` ... ``:::``, stripped for non-GM readers."""

import re

#: Python twin of ``app.constants.ARTICLE_GM_BLOCK_SQL_PATTERN`` (used by the generated
#: ``search_vector`` column); case-insensitive (``:::GM`` too), an unclosed block runs to the end of
#: the text (fail closed).
GM_BLOCK_RE = re.compile(r":::gm.*?(?::::|\Z)", re.DOTALL | re.IGNORECASE)


def strip_gm_blocks(text: str | None) -> str | None:
    """Return ``text`` (body, excerpt, relation note) with every GM-only block removed; ``None`` stays ``None``."""

    return GM_BLOCK_RE.sub("", text) if text else text
