"""GM-only blocks inside an article body: ``:::gm`` ... ``:::``, stripped for non-GM readers."""

import re

#: Python twin of ``app.constants.ARTICLE_GM_BLOCK_SQL_PATTERN`` (used by the generated
#: ``search_vector`` column); an unclosed block runs to the end of the text (fail closed).
GM_BLOCK_RE = re.compile(r":::gm.*?(?::::|\Z)", re.DOTALL)


def strip_gm_blocks(body: str) -> str:
    """Return ``body`` with every GM-only block removed."""

    return GM_BLOCK_RE.sub("", body)
