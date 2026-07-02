"""Shared text utilities used across stages."""

from __future__ import annotations

import re

STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "into", "are",
    "was", "were", "how", "why", "what", "which", "when", "where", "who",
    "whom", "whose", "does", "did", "can", "could", "would", "should",
    "must", "may", "might", "have", "has", "had", "but", "not", "nor",
    "you", "your", "yours", "they", "their", "them", "our", "its",
    "about", "there", "here", "over", "under", "out", "off", "any",
    "some", "all", "most", "more", "less", "than", "then", "such",
})


def tokenize(text: str) -> set[str]:
    """Lowercase, alphanumeric tokens of length >=3, minus stopwords."""
    tokens = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in STOPWORDS}
