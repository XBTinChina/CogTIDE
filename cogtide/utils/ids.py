"""Stable ID and slug helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime


def stable_hash(s: str) -> int:
    """Deterministic 32-bit hash of a string, stable across interpreter runs.

    Python's built-in ``hash()`` of a string is randomized by
    ``PYTHONHASHSEED`` (default random since 3.3), which makes any code
    that uses it for tie-breaking non-deterministic across runs. Stage 2
    coalition selection and Stage 3 council selection both need stable
    tie-breaking so the same input produces the same coalitions/councils
    every time; this helper is the replacement.
    """
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:4], "big")


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:max_len] or "untitled"


def timestamp_now() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def make_run_id(topic_slug: str) -> str:
    return f"run_{topic_slug}_{timestamp_now()}"


def idea_id(index: int) -> str:
    return f"I{index:03d}"


def deep_theory_id(index: int) -> str:
    return f"D{index:02d}"


def unit_id(index: int) -> str:
    return f"U{index:02d}"


def kernel_id(index: int) -> str:
    return f"K{index:02d}"


def theory_id(index: int) -> str:
    return f"T{index:02d}"
