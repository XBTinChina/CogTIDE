"""Unit tests for cogtide.llm.normalization.

Pure-logic tests for JSON extraction from raw LLM text and the
list/string coercion helpers. No network, no filesystem.
"""

from __future__ import annotations

from cogtide.llm.normalization import (
    coerce_list_field,
    coerce_string_field,
    ensure_list,
    extract_json,
    safe_join,
    safe_str,
)


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------


def test_extract_json_fenced_array():
    parsed, report = extract_json("```json\n[1, 2, 3]\n```")
    assert parsed == [1, 2, 3]
    assert report.used_fence is True
    assert report.parse_succeeded is True


def test_extract_json_bare_object():
    parsed, report = extract_json('{"a": 1, "b": 2}', expect="object")
    assert parsed == {"a": 1, "b": 2}
    assert report.parse_succeeded is True
    assert report.unwrapped_key is None


def test_extract_json_unwraps_known_array_wrapper():
    parsed, report = extract_json('{"ideas": [{"x": 1}]}', expect="auto")
    assert parsed == [{"x": 1}]
    assert report.unwrapped_key == "ideas"


def test_extract_json_unwraps_single_list_fallback():
    parsed, report = extract_json('{"weird_key": [1, 2]}', expect="auto")
    assert parsed == [1, 2]
    assert report.unwrapped_key == "fallback:weird_key"


def test_extract_json_unwraps_object_wrapper():
    parsed, report = extract_json('{"deep_theory": {"name": "X"}}', expect="object")
    assert parsed == {"name": "X"}
    assert report.unwrapped_key == "object:deep_theory"


def test_extract_json_regex_fallback():
    parsed, report = extract_json("Sure! Here you go: [1, 2, 3] hope that helps")
    assert parsed == [1, 2, 3]
    assert report.used_regex_fallback is True
    assert report.parse_succeeded is True


def test_extract_json_total_failure_returns_cleaned_text():
    text = "there is no json here at all"
    parsed, report = extract_json(text)
    assert parsed == text
    assert report.parse_succeeded is False
    assert report.json_decode_errors  # at least one decode error recorded


# ---------------------------------------------------------------------------
# ensure_list / safe_str / safe_join / coercers
# ---------------------------------------------------------------------------


def test_ensure_list_variants():
    assert ensure_list([1, 2]) == [1, 2]
    assert ensure_list("x") == ["x"]
    assert ensure_list(None) == []
    assert ensure_list(5) == [5]


def test_safe_str_variants():
    assert safe_str("hi") == "hi"
    assert safe_str(["a", "b"]) == "a, b"
    assert safe_str({"a": 1}) == '{"a": 1}'
    assert safe_str(None) == ""
    assert safe_str("hello", max_len=3) == "hel"


def test_safe_join_list_and_scalar():
    assert safe_join(["a", "b"], sep="|") == "a|b"
    assert safe_join("already a string") == "already a string"


def test_coerce_list_field_filters_empty_and_none():
    assert coerce_list_field(["a", "", None, "b"]) == ["a", "b"]
    assert coerce_list_field("x") == ["x"]
    assert coerce_list_field(None) == []


def test_coerce_string_field_on_dict():
    assert coerce_string_field({"k": "v"}) == '{"k": "v"}'
