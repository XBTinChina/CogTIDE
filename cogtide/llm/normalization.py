"""Normalization boundary between raw LLM output and stage logic.

Wraps JSON extraction and list/string coercion in a NormalizationReport
object so every parse step applied to raw model output is auditable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Top-level wrapper keys we have seen LLMs add around array payloads.
WRAPPER_KEYS = (
    "theories",
    "results",
    "data",
    "response",
    "models",
    "challenges",
    "critiques",
    "feedback",
    "links",
    "comparisons",
    "evaluations",
    "ideas",
    "units",
    "kernels",
    "experts",
    "items",
    "list",
    "output",
    "answer",
    "reviews",
    "ratings",
    "predictions",
    "scorecards",
    "variants",
)

# Wrapper keys we have seen LLMs add around OBJECT payloads (as opposed
# to array payloads). Stage 2/3/4 facilitator and judge calls all expect
# a single JSON object as the candidate, and LLMs sometimes wrap it in
# things like ``{"deep_theory": {...}}`` or ``{"draft": {...}}``. The
# object-unwrap branch in ``extract_json`` walks this list in order.
OBJECT_WRAPPER_KEYS = (
    "deep_theory",
    "deep_theories",
    "draft",
    "candidate",
    "kernel",
    "theory",
    "triplet",
    "review",
    "peer_review",
    "prediction",
    "verdict",
    "scorecard",
    "output",
    "result",
    "response",
    "data",
    "answer",
)


@dataclass
class NormalizationReport:
    """Audit record for one normalization pass."""

    raw_text: str
    parsed: Any = None
    used_fence: bool = False
    used_regex_fallback: bool = False
    unwrapped_key: str | None = None
    json_decode_errors: list[str] = field(default_factory=list)
    parse_succeeded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "parse_succeeded": self.parse_succeeded,
            "used_fence": self.used_fence,
            "used_regex_fallback": self.used_regex_fallback,
            "unwrapped_key": self.unwrapped_key,
            "json_decode_errors": self.json_decode_errors,
            "raw_text_len": len(self.raw_text),
        }


def extract_json(text: str, expect: str = "auto") -> tuple[Any, NormalizationReport]:
    """Extract JSON from LLM response text.

    Handles markdown code fences, bare JSON, and unwraps top-level wrapper
    objects when an array payload is expected.

    Args:
        text: raw LLM output.
        expect: "array", "object", or "auto". When "array", a wrapper-object
            unwrap is attempted; when "object", no unwrap is performed.

    Returns:
        (parsed_value, NormalizationReport). On total failure, parsed_value
        falls back to the cleaned text and parse_succeeded is False.
    """
    report = NormalizationReport(raw_text=text)

    # 1. Strip markdown fence if present.
    body = text
    fence_match = re.search(r"```(?:json|yaml|JSON)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        body = fence_match.group(1).strip()
        report.used_fence = True

    # 2. Try direct json.loads.
    parsed: Any = None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        report.json_decode_errors.append(str(e))
        # 3. Regex fallback for embedded JSON.
        for pattern in (r"(\[.*\])", r"(\{.*\})"):
            m = re.search(pattern, body, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(1))
                    report.used_regex_fallback = True
                    break
                except json.JSONDecodeError as e2:
                    report.json_decode_errors.append(str(e2))
                    continue

    if parsed is None:
        report.parsed = body
        return body, report

    # 4. Unwrap wrapper-object when array expected.
    if expect != "object" and isinstance(parsed, dict):
        unwrapped = False
        # 4a. Try known wrapper keys first.
        for key in WRAPPER_KEYS:
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                report.unwrapped_key = key
                unwrapped = True
                break
        # 4b. Fallback: when json_object response_format forces a top-level
        # object, the model may pick an unexpected wrapper key. If the dict
        # has exactly one list-valued field, treat it as the wrapper.
        if not unwrapped:
            list_keys = [k for k, v in parsed.items() if isinstance(v, list)]
            if len(list_keys) == 1:
                key = list_keys[0]
                parsed = parsed[key]
                report.unwrapped_key = f"fallback:{key}"

    # 5. Unwrap wrapper-object when a single object is expected. LLMs
    # sometimes wrap facilitator/judge output in keys like
    # ``{"deep_theory": {...}}`` or ``{"draft": {...}}``. We only unwrap
    # when we find a known wrapper key whose value is itself a dict —
    # we deliberately do NOT do the aggressive "single dict-valued field"
    # fallback here because it would eat ordinary payloads that happen
    # to have one nested object.
    if expect == "object" and isinstance(parsed, dict):
        for key in OBJECT_WRAPPER_KEYS:
            if key in parsed and isinstance(parsed[key], dict):
                parsed = parsed[key]
                report.unwrapped_key = f"object:{key}"
                break

    report.parsed = parsed
    report.parse_succeeded = True
    return parsed, report


def ensure_list(value: Any) -> list:
    """Coerce a value to a list. Handles LLMs returning a string for a list field."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    if value is None:
        return []
    return [value]


def safe_str(value: Any, max_len: int = 0) -> str:
    """Coerce any value to string. Handles dicts, lists, None."""
    if isinstance(value, str):
        s = value
    elif isinstance(value, list):
        s = ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        s = json.dumps(value, ensure_ascii=False)
    elif value is None:
        s = ""
    else:
        s = str(value)
    if max_len > 0 and len(s) > max_len:
        return s[:max_len]
    return s


def safe_join(values: Any, sep: str = ", ", item_max: int = 0) -> str:
    """Safely join a value that might be a list, string, or scalar."""
    if isinstance(values, str):
        return values[:item_max] if item_max > 0 else values
    if isinstance(values, list):
        items: list[str] = []
        for v in values:
            s = v if isinstance(v, str) else str(v)
            if item_max > 0:
                s = s[:item_max]
            items.append(s)
        return sep.join(items)
    return str(values) if values else ""


def coerce_string_field(value: Any) -> str:
    """Pydantic-friendly coercer for fields that should be strings."""
    return safe_str(value)


def coerce_list_field(value: Any) -> list:
    """Pydantic-friendly coercer for fields that should be lists of strings."""
    items = ensure_list(value)
    return [safe_str(x) for x in items if x not in (None, "")]
