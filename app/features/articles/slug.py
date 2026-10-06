"""Slug generation for articles: transliterate a title to a URL-safe ASCII slug."""

import re

# Russian + Ukrainian Cyrillic -> Latin (no third-party transliteration dependency in the project).
_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e", "є": "ye", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip

SLUG_MAX_LENGTH = 200  # column is String(220); leaves room for a "-N" collision suffix
FALLBACK_SLUG = "article"

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """
    Turn ``title`` into a lowercase ASCII slug (``"Кхазад-дум"`` -> ``"khazad-dum"``).

    Returns ``FALLBACK_SLUG`` when nothing usable remains (e.g. a title of only symbols).
    """

    transliterated = "".join(_CYRILLIC_TO_LATIN.get(char, char) for char in title.lower())
    slug = _NON_SLUG.sub("-", transliterated).strip("-")[:SLUG_MAX_LENGTH].strip("-")

    return slug or FALLBACK_SLUG
