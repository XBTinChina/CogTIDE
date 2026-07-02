"""Field-alias canonicalization for LLM responses.

LLMs drift toward field names they have recently seen. Any name in
the input payload is a candidate to leak into the output. Any sibling
schema's field name is a candidate to leak into the output. This
module is the rescue layer that maps known aliases back to the
canonical field names **before** Pydantic validation runs.

Order of operations expected by callers:

    raw_dict -> envelope unwrap (normalization.extract_json)
             -> canonicalize(..., aliases=..., required=...)
             -> Model.from_normalized(canonical_dict)

Each alias tuple lists the canonical name first, then known
leak-source aliases. The first key in the tuple that is present with
a non-empty value wins. Empty values are treated as absent, which
both rejects blank fields and lets a later alias in the tuple rescue
a rename that also dropped its value.
"""

from __future__ import annotations

from typing import Any

from .normalization import OBJECT_WRAPPER_KEYS

# Stage 1 raw idea canonical output (Stage1Idea.from_normalized).
STAGE1_IDEA_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "idea_title", "short_name"),
    "core_claim": (
        "core_claim",
        "claim",
        "main_claim",
        "central_claim",
        "core",
    ),
    "mechanism": (
        "mechanism",
        "mechanism_sketch",
        "mechanism_description",
        "proposed_mechanism",
    ),
    "explains": (
        "explains",
        "explains_list",
        "explanations",
        "what_it_explains",
    ),
    "main_assumptions": (
        "main_assumptions",
        "assumptions",
        "key_assumptions",
    ),
    "distinctive_prediction": (
        "distinctive_prediction",
        "prediction",
        "key_prediction",
        "distinguishing_prediction",
        "distinctive_predictions",
    ),
    "why_interesting": (
        "why_interesting",
        "why",
        "motivation",
        "significance",
        "why_it_matters",
    ),
    "risk_level": (
        "risk_level",
        "risk",
        "level",
        "risk_tier",
    ),
}

STAGE1_IDEA_REQUIRED: set[str] = {
    "title",
    "core_claim",
    "mechanism",
    "distinctive_prediction",
    "why_interesting",
    "risk_level",
}

# Stage 1 challenger critique canonical output.
STAGE1_CHALLENGE_ALIASES: dict[str, tuple[str, ...]] = {
    "idea_id": ("idea_id", "id", "target_idea_id"),
    "critiques": ("critiques", "critique", "issues", "points"),
    "severity": ("severity", "level", "priority"),
    "suggested_revision": (
        "suggested_revision",
        "suggestion",
        "revision",
        "recommendation",
    ),
}

STAGE1_CHALLENGE_REQUIRED: set[str] = {"idea_id", "severity"}

# Stage 2 deep-theory canonical output (Stage2DeepTheory.from_normalized).
STAGE2_DEEP_THEORY_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "title", "deep_theory_name", "theory_name"),
    "deep_theory_statement": (
        "deep_theory_statement",
        "statement",
        "core_claim",
        "claim",
    ),
    "rationale": (
        "rationale",
        "why_interesting",
        "why_deeper",
        "why_this_is_deeper",
    ),
    "mechanism_sketch": (
        "mechanism_sketch",
        "mechanism",
        "mechanism_description",
    ),
    "key_predictions": (
        "key_predictions",
        "predictions",
        "distinctive_predictions",
        "distinctive_prediction",
    ),
    "key_assumptions": (
        "key_assumptions",
        "main_assumptions",
        "assumptions",
    ),
    "tensions_and_open_questions": (
        "tensions_and_open_questions",
        "open_questions",
        "tensions",
    ),
    "discussion_summary": (
        "discussion_summary",
        "summary",
        "coalition_summary",
    ),
}

STAGE2_DEEP_THEORY_REQUIRED: set[str] = {
    "name",
    "deep_theory_statement",
    "rationale",
}

STAGE2_DRAFT_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "title", "draft_name"),
    "deep_theory_statement": (
        "deep_theory_statement",
        "statement",
        "draft_statement",
        "core_claim",
        "claim",
    ),
    "mechanism_sketch": (
        "mechanism_sketch",
        "mechanism",
        "mechanism_description",
    ),
}

STAGE2_DRAFT_REQUIRED: set[str] = {
    "deep_theory_statement",
    "mechanism_sketch",
}

STAGE3_KERNEL_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "title", "kernel_name"),
    "kernel_statement": (
        "kernel_statement",
        "statement",
        "deep_theory_statement",
    ),
    "deeper_substrate": (
        "deeper_substrate",
        "substrate",
        "shared_architecture",
    ),
    "rationale": ("rationale", "why_deeper", "why_interesting"),
    "mechanism_sketch": ("mechanism_sketch", "mechanism"),
    "key_predictions": (
        "key_predictions",
        "predictions",
        "distinctive_predictions",
    ),
    "key_assumptions": (
        "key_assumptions",
        "main_assumptions",
        "assumptions",
    ),
    "preserved_tensions": (
        "preserved_tensions",
        "tensions_and_open_questions",
        "open_questions",
    ),
    "discussion_summary": (
        "discussion_summary",
        "summary",
        "council_summary",
    ),
}

STAGE3_KERNEL_REQUIRED: set[str] = {
    "name",
    "kernel_statement",
    "deeper_substrate",
    "rationale",
}

STAGE4_THEORY_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "title", "theory_name"),
    "statement": (
        "statement",
        "kernel_statement",
        "theory_statement",
    ),
    "central_claim": (
        "central_claim",
        "central_explanatory_claim",
        "core_claim",
        "claim",
    ),
    "ontology": (
        "ontology",
        "variables",
        "entities",
        "constructs",
    ),
    "mechanism": (
        "mechanism",
        "mechanism_sketch",
        "mechanism_description",
        "causal_mechanism",
    ),
    "formal_sketch": (
        "formal_sketch",
        "formalization",
        "model_sketch",
        "mathematical_sketch",
    ),
    "boundary_conditions": (
        "boundary_conditions",
        "scope_conditions",
        "applicability",
    ),
    "main_assumptions": (
        "main_assumptions",
        "key_assumptions",
        "assumptions",
    ),
    "distinctive_predictions": (
        "distinctive_predictions",
        "key_predictions",
        "predictions",
        "distinctive_prediction",
    ),
    "testable_predictions": (
        "testable_predictions",
        "quantitative_predictions",
        "operational_predictions",
    ),
    "falsifiers": (
        "falsifiers",
        "falsifying_observations",
        "falsification_conditions",
    ),
    "measurement_strategy": (
        "measurement_strategy",
        "operationalization",
        "measurement",
    ),
    "phenomena_explained": (
        "phenomena_explained",
        "explains",
        "explananda",
    ),
    "open_questions": (
        "open_questions",
        "tensions_and_open_questions",
        "unresolved_questions",
    ),
    "notes": ("notes", "commentary", "remark"),
}

STAGE4_THEORY_REQUIRED: set[str] = {
    "name",
    "statement",
    "central_claim",
    "mechanism",
}

# ── v2 peer-review canonicalization ──────────────────────────────────────

PEER_REVIEW_ALIASES: dict[str, tuple[str, ...]] = {
    "overall_quality": ("overall_quality", "quality", "score", "overall_score"),
    "brief_assessment": ("brief_assessment", "assessment", "summary", "review"),
    "strengths": ("strengths", "pros", "positive_points"),
    "failure_modes": ("failure_modes", "weaknesses", "cons", "failure_points", "risks"),
}

PEER_REVIEW_REQUIRED: set[str] = {
    "overall_quality",
}

PEER_PREDICTION_ALIASES: dict[str, tuple[str, ...]] = {
    "predicted_avg_quality": (
        "predicted_avg_quality",
        "predicted_quality",
        "expected_quality",
        "predicted_average",
    ),
    "predicted_survival_probability": (
        "predicted_survival_probability",
        "survival_probability",
        "predicted_survival",
        "survival_forecast",
    ),
    "overrated_underrated": (
        "overrated_underrated",
        "over_under",
        "rating_bias",
    ),
}

PEER_PREDICTION_REQUIRED: set[str] = {
    "predicted_avg_quality",
}

JUDGE_VERDICT_ALIASES: dict[str, tuple[str, ...]] = {
    "verdict": ("verdict", "decision", "accepted", "accept"),
    "judge_notes": ("judge_notes", "notes", "explanation", "reasoning"),
    "rejection_reason": (
        "rejection_reason",
        "reason",
        "failure_reason",
        "reject_reason",
    ),
}

JUDGE_VERDICT_REQUIRED: set[str] = {
    "verdict",
}


def _is_empty_value(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) == 0
    return False


def canonicalize(
    raw: dict,
    *,
    aliases: dict[str, tuple[str, ...]],
    required: set[str],
) -> tuple[dict[str, Any], list[str]]:
    corrections: list[str] = []
    src: dict[str, Any] = raw if isinstance(raw, dict) else {}

    for wrapper in OBJECT_WRAPPER_KEYS:
        inner = src.get(wrapper)
        if isinstance(inner, dict):
            corrections.append(f"unwrapped envelope key '{wrapper}'")
            src = inner
            break

    known_alias_keys: set[str] = set()
    for alt_keys in aliases.values():
        for k in alt_keys:
            known_alias_keys.add(k)

    out: dict[str, Any] = {}
    for canonical, alt_keys in aliases.items():
        for k in alt_keys:
            if k in src and not _is_empty_value(src[k]):
                out[canonical] = src[k]
                if k != canonical:
                    corrections.append(f"renamed '{k}' -> '{canonical}'")
                break

    for k, v in src.items():
        if k in known_alias_keys:
            continue
        if k in out:
            continue
        out[k] = v

    missing = sorted(k for k in required if _is_empty_value(out.get(k)))
    if missing:
        corrections.append(f"missing/blank required fields: {missing}")

    return out, corrections


def is_canonicalization_ok(corrections: list[str]) -> bool:
    return not any(c.startswith("missing/blank") for c in corrections)
