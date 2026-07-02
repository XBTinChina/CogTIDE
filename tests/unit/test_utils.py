"""Unit tests for cogtide.utils.ids and cogtide.utils.text.

Pure helpers: slugs, stable hashing, ID formatting, run-id/timestamp
shape, and tokenization. No network, no filesystem.
"""

from __future__ import annotations

import re

from cogtide.utils.ids import (
    deep_theory_id,
    idea_id,
    kernel_id,
    make_run_id,
    slugify,
    stable_hash,
    theory_id,
    timestamp_now,
    unit_id,
)
from cogtide.utils.text import tokenize


# ---------------------------------------------------------------------------
# ids
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_empty_falls_back():
    assert slugify("   ") == "untitled"
    assert slugify("!!!") == "untitled"


def test_slugify_truncates_to_max_len():
    assert slugify("abcdefghij", max_len=5) == "abcde"


def test_id_formatters_are_zero_padded():
    assert idea_id(7) == "I007"
    assert deep_theory_id(3) == "D03"
    assert unit_id(5) == "U05"
    assert kernel_id(12) == "K12"
    assert theory_id(1) == "T01"


def test_stable_hash_is_deterministic_and_bounded():
    h1 = stable_hash("working memory")
    h2 = stable_hash("working memory")
    assert isinstance(h1, int)
    assert h1 == h2
    assert 0 <= h1 < 2 ** 32
    assert stable_hash("working memory") != stable_hash("attention")


def test_timestamp_now_shape():
    ts = timestamp_now()
    assert re.fullmatch(r"\d{8}_\d{6}", ts)


def test_make_run_id_prefix():
    rid = make_run_id("mytopic")
    assert rid.startswith("run_mytopic_")
    assert re.fullmatch(r"run_mytopic_\d{8}_\d{6}", rid)


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------


def test_tokenize_drops_stopwords_and_short_tokens():
    toks = tokenize("The quick brown fox jumps")
    assert toks == {"quick", "brown", "fox", "jumps"}
    assert "the" not in toks


def test_tokenize_lowercases_and_splits_nonalnum():
    toks = tokenize("Working-Memory & Attention!")
    assert toks == {"working", "memory", "attention"}
