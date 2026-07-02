"""Unit tests for the pure Stage 0 context helpers.

Covers subfolder token scoring and text-file ingestion. All filesystem
access is confined to pytest's tmp_path; no network, no LLM calls.
"""

from __future__ import annotations

from cogtide.stages.stage_00 import (
    _tokenize,
    read_context_from_folder,
    score_subfolders_against_topic,
)


def test_tokenize_matches_text_util_behavior():
    toks = _tokenize("The Working-Memory system")
    assert toks == {"working", "memory", "system"}


def test_score_subfolders_by_name_overlap(tmp_path):
    good = tmp_path / "working-memory-attention"
    bad = tmp_path / "cooking-recipes"
    good.mkdir()
    bad.mkdir()

    scored = score_subfolders_against_topic(
        "How does working memory support attention?",
        [good, bad],
    )
    # Only the matching folder is returned; the zero-overlap one is dropped.
    assert len(scored) == 1
    assert scored[0][0].name == "working-memory-attention"
    assert scored[0][1] == 3  # working, memory, attention


def test_score_subfolders_no_match_returns_empty(tmp_path):
    folder = tmp_path / "cooking-recipes"
    folder.mkdir()
    assert score_subfolders_against_topic("quantum gravity", [folder]) == []


def test_read_context_concatenates_and_filters(tmp_path):
    folder = tmp_path / "ctx"
    folder.mkdir()
    (folder / "a.md").write_text("Alpha content", encoding="utf-8")
    (folder / "b.txt").write_text("Beta content", encoding="utf-8")
    (folder / "overview.md").write_text("SHOULD BE IGNORED", encoding="utf-8")
    (folder / "image.png").write_bytes(b"\x89PNG binary")

    text = read_context_from_folder(folder)

    assert "Alpha content" in text
    assert "Beta content" in text
    assert "--- a.md ---" in text
    assert "--- b.txt ---" in text
    # overview.md is on the ignore list; binary .png is skipped by extension.
    assert "SHOULD BE IGNORED" not in text
    assert "PNG binary" not in text


def test_read_context_respects_char_budget(tmp_path):
    folder = tmp_path / "ctx"
    folder.mkdir()
    (folder / "a.md").write_text("Alpha content that is fairly long", encoding="utf-8")

    # A tiny budget cannot even fit the first file's header, so nothing is read.
    text = read_context_from_folder(folder, max_total_chars=5)
    assert text == ""


def test_read_context_missing_folder_returns_empty(tmp_path):
    assert read_context_from_folder(tmp_path / "does-not-exist") == ""
