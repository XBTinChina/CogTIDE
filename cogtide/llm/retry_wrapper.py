"""Retry-with-pointed-correction wrapper for structured LLM calls."""

from __future__ import annotations

import json
from typing import Any, Callable

from .canonicalization import canonicalize, is_canonicalization_ok
from .client import CallRecord


async def call_json_with_retry(
    ctx: Any,
    *,
    agent_id: str,
    system_prompt: str,
    payload: dict[str, Any],
    aliases: dict[str, tuple[str, ...]],
    required: set[str],
    expect: str = "object",
    max_attempts: int = 3,
    soft_fail_predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[dict[str, Any] | None, CallRecord | None, list[str]]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    errors: list[str] = []
    last_record: CallRecord | None = None
    last_canonical: dict[str, Any] | None = None

    base_payload = dict(payload)
    required_list = sorted(required)

    for attempt in range(1, max_attempts + 1):
        current_payload: dict[str, Any] = dict(base_payload)
        current_payload["attempt"] = attempt
        current_payload["max_attempts"] = max_attempts

        if attempt > 1 and errors:
            current_payload["previous_response_was_invalid"] = True
            current_payload["previous_failure_reasons"] = errors[-3:]
            current_payload["instructions_for_retry"] = (
                "Your previous response was rejected for the reasons "
                "listed in `previous_failure_reasons`. Re-emit a single "
                "JSON object with the canonical field names exactly as "
                "specified in the output contract. Required canonical "
                f"fields (must be non-empty): {required_list}. Do NOT "
                "wrap the response in an envelope like `deep_theory`, "
                "`draft`, `kernel`, `theory`, or `triplet`. Do NOT echo "
                "field names from the input ideas (e.g. `core_claim`, "
                "`mechanism`, `main_assumptions`, `distinctive_prediction`) "
                "into the output."
            )

        user_message = json.dumps(current_payload, ensure_ascii=False)
        parsed, record = await ctx.client.chat_json(
            agent_id=(
                f"{agent_id}_attempt{attempt}" if attempt > 1 else agent_id
            ),
            system_prompt=system_prompt,
            user_message=user_message,
            expect=expect,
        )
        last_record = record

        if not record.succeeded:
            errors.append(
                f"transport failure on attempt {attempt}: {record.last_error}"
            )
            return None, record, errors

        if not isinstance(parsed, dict):
            errors.append(
                f"attempt {attempt}: parsed output is not a dict "
                f"(type={type(parsed).__name__})"
            )
            continue

        if soft_fail_predicate is not None and soft_fail_predicate(parsed):
            reason = parsed.get("failure_reason") or parsed.get("reason") or ""
            note = (
                f"attempt {attempt}: soft failure declared by agent"
                + (f" ({reason})" if reason else "")
            )
            errors.append(note)
            return None, record, errors

        canonical, corrections = canonicalize(
            parsed, aliases=aliases, required=required
        )
        last_canonical = canonical

        if is_canonicalization_ok(corrections):
            return canonical, record, corrections

        missing_entry = next(
            (c for c in corrections if c.startswith("missing/blank")),
            "missing/blank required fields",
        )
        errors.append(f"attempt {attempt}: {missing_entry}")

    return last_canonical, last_record, errors
