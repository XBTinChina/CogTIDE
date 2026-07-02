"""Blind peer review orchestration.

Manages the collection of blind peer ratings and predictions from
expert agents who did not author or synthesize the item under review.

Key principle: reviewers never see other reviewers' ratings before
submitting their own. This is what makes the peer-prediction signal
informative — predictions about peer opinion are made independently.
"""

from __future__ import annotations

import json
import random
from typing import Any

from cogtide.llm.client import LLMClient, gather_with_limit
from cogtide.utils.ids import stable_hash
from cogtide.models.review_signals import (
    DimensionRating,
    PeerRating,
    PeerPrediction,
    PeerReviewEnvelope,
    IdeaPeerReviewSet,
    TheoryPeerReviewSet,
    TripletPeerReview,
    ReviewTargetKind,
)

# Default quality dimensions for each target kind
IDEA_DIMENSIONS = [
    "novelty",
    "mechanistic_promise",
    "coherence",
    "distinctiveness",
    "testability",
]

THEORY_DIMENSIONS = [
    "depth",
    "mechanistic_clarity",
    "coherence",
    "distinctiveness",
    "testability",
    "non_averaging",
]

TRIPLET_DIMENSIONS = [
    "coherence",
    "defensibility",
    "novelty",
    "distinctiveness",
    "experimental_fertility",
    "upside_if_true",
]


def _safe_float(value: Any, default: float) -> float:
    """Coerce a numeric field from raw LLM output, falling back on junk.

    LLMs occasionally emit ``null``, a nested ``{"score": ...}`` object, or
    a non-numeric string where a number belongs. One malformed review must
    not abort a whole gather batch, so every numeric field goes through
    this coercion instead of a bare ``float()`` cast.
    """
    if isinstance(value, dict):
        value = value.get("score", default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _select_reviewers(
    all_expert_ids: list[str],
    exclude_ids: set[str],
    n_reviewers: int,
    seed: int,
) -> list[str]:
    """Select reviewers who did not author the item, seeded for determinism."""
    eligible = [eid for eid in all_expert_ids if eid not in exclude_ids]
    rng = random.Random(seed)
    rng.shuffle(eligible)
    return eligible[:n_reviewers]


def _parse_review_response(
    raw: dict[str, Any],
    reviewer_id: str,
    target_id: str,
    target_kind: ReviewTargetKind,
    dimensions: list[str],
) -> PeerReviewEnvelope:
    """Parse an LLM review response into a PeerReviewEnvelope."""
    # Parse direct ratings
    raw_ratings = raw.get("ratings", {})
    dim_ratings = []
    for dim in dimensions:
        dim_ratings.append(DimensionRating(
            dimension=dim,
            score=_safe_float(raw_ratings.get(dim), 5.0) or 5.0,
            confidence=_safe_float(raw_ratings.get(f"{dim}_confidence"), 0.5),
            note=str(raw_ratings.get(f"{dim}_note", "")),
        ))

    rating = PeerRating(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind=target_kind,
        ratings=dim_ratings,
        overall_quality=_safe_float(raw.get("overall_quality"), 5.0),
        failure_modes=_as_list(raw.get("failure_modes", [])),
        strengths=_as_list(raw.get("strengths", [])),
        brief_assessment=str(raw.get("brief_assessment", "")),
    )

    # Parse predictions
    raw_preds = raw.get("predictions", {})
    pred_dim_avgs = []
    pred_ratings = raw_preds.get("predicted_dimension_avgs", {})
    for dim in dimensions:
        pred_dim_avgs.append(DimensionRating(
            dimension=dim,
            score=_safe_float(pred_ratings.get(dim), 5.0) or 5.0,
        ))

    ou_raw = str(raw_preds.get("overrated_underrated", "fair")).lower()
    if "under" in ou_raw:
        ou_val = "underrated"
    elif "over" in ou_raw:
        ou_val = "overrated"
    else:
        ou_val = "fair"

    prediction = PeerPrediction(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind=target_kind,
        predicted_avg_quality=_safe_float(
            raw_preds.get("predicted_avg_quality"), 5.0
        ),
        predicted_dimension_avgs=pred_dim_avgs,
        predicted_survival_probability=_safe_float(
            raw_preds.get("predicted_survival_probability"), 0.5
        ),
        predicted_survival_rationale=str(
            raw_preds.get("predicted_survival_rationale", "")
        ),
        overrated_underrated=ou_val,  # type: ignore[arg-type]
        overrated_underrated_rationale=str(
            raw_preds.get("overrated_underrated_rationale", "")
        ),
    )

    return PeerReviewEnvelope(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind=target_kind,
        rating=rating,
        prediction=prediction,
    )


def _as_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str) and val:
        return [val]
    return []


def _build_idea_review_payload(idea: dict[str, Any], dimensions: list[str]) -> dict[str, Any]:
    """Build the user-message payload for reviewing one idea."""
    return {
        "task": "blind_peer_review",
        "target_kind": "idea",
        "target_id": idea.get("id", ""),
        "target": {
            "id": idea.get("id", ""),
            "title": idea.get("title", ""),
            "core_claim": idea.get("core_claim", ""),
            "mechanism": idea.get("mechanism", ""),
            "explains": idea.get("explains", []),
            "distinctive_prediction": idea.get("distinctive_prediction", ""),
            "risk_level": idea.get("risk_level", ""),
        },
        "dimensions_to_rate": dimensions,
        "instructions": (
            "Rate this idea on each dimension (1-10). Then predict what "
            "the average reviewer will give on each dimension and overall. "
            "Predict whether this idea will contribute to an accepted "
            "deep theory downstream. Judge whether it is overrated, "
            "underrated, or fairly rated relative to likely peer opinion."
        ),
    }


def _build_theory_review_payload(
    theory: dict[str, Any],
    target_kind: str,
    dimensions: list[str],
) -> dict[str, Any]:
    """Build the user-message payload for reviewing a deep theory or kernel."""
    return {
        "task": "blind_peer_review",
        "target_kind": target_kind,
        "target_id": theory.get("id", ""),
        "target": theory,
        "dimensions_to_rate": dimensions,
        "instructions": (
            f"Rate this {target_kind} on each dimension (1-10). Then predict "
            "what the average reviewer will give on each dimension and overall. "
            f"Predict whether this {target_kind} will survive the next stage. "
            "Judge whether it is overrated, underrated, or fairly rated. "
            "Flag if it seems only locally persuasive (sounds good within "
            "its own framing but would not convince an outsider)."
        ),
    }


async def _collect_single_review(
    client: LLMClient,
    reviewer_id: str,
    system_prompt: str,
    payload: dict[str, Any],
    target_id: str,
    target_kind: ReviewTargetKind,
    dimensions: list[str],
) -> PeerReviewEnvelope | None:
    """Run one blind peer review call and parse the result."""
    user_message = json.dumps(payload, ensure_ascii=False)
    parsed, record = await client.chat_json(
        agent_id=f"peer_reviewer_{reviewer_id}_{target_id}",
        system_prompt=system_prompt,
        user_message=user_message,
        expect="object",
    )
    if not record.succeeded or not isinstance(parsed, dict):
        return None
    return _parse_review_response(
        parsed, reviewer_id, target_id, target_kind, dimensions
    )


async def run_idea_peer_review(
    client: LLMClient,
    ideas: list[dict[str, Any]],
    all_expert_ids: list[str],
    *,
    n_reviewers_per_idea: int = 5,
    seed: int = 42,
    system_prompt: str = "",
    max_concurrency: int = 6,
) -> IdeaPeerReviewSet:
    """Run blind peer reviews on all Stage 1 ideas.

    Each idea is reviewed by n_reviewers_per_idea experts who did NOT
    author the idea. Reviews are collected in parallel.
    """
    all_reviews: list[PeerReviewEnvelope] = []
    all_reviewer_ids: set[str] = set()
    reviewed_ids: list[str] = []

    coros = []
    review_meta: list[tuple[str, str]] = []  # (target_id, reviewer_id)

    for idea in ideas:
        idea_id = idea.get("id", "")
        author = idea.get("source_lens", "")
        exclude = {author} if author else set()
        reviewers = _select_reviewers(
            all_expert_ids, exclude, n_reviewers_per_idea,
            seed=seed + stable_hash(idea_id) % 10000,
        )
        reviewed_ids.append(idea_id)
        for rev_id in reviewers:
            all_reviewer_ids.add(rev_id)
            payload = _build_idea_review_payload(idea, IDEA_DIMENSIONS)
            coros.append(_collect_single_review(
                client, rev_id, system_prompt, payload,
                idea_id, "idea", IDEA_DIMENSIONS,
            ))
            review_meta.append((idea_id, rev_id))

    results = await gather_with_limit(coros, max_concurrency=max_concurrency)

    for env in results:
        if env is not None:
            all_reviews.append(env)

    return IdeaPeerReviewSet(
        reviews=all_reviews,
        reviewer_ids=sorted(all_reviewer_ids),
        reviewed_idea_ids=reviewed_ids,
        reviews_per_idea=n_reviewers_per_idea,
    )


async def run_theory_peer_panel(
    client: LLMClient,
    theories: list[dict[str, Any]],
    panel_expert_ids: list[str],
    *,
    target_kind: ReviewTargetKind = "deep_theory",
    system_prompt: str = "",
    max_concurrency: int = 6,
) -> TheoryPeerReviewSet:
    """Run an external peer panel on deep theories or kernels.

    Every panelist reviews every theory. Panel members must not have
    participated in synthesizing the theories.
    """
    dims = THEORY_DIMENSIONS
    panel_kind = f"stage2_external" if target_kind == "deep_theory" else "stage3_external"

    coros = []
    for theory in theories:
        tid = theory.get("id", "")
        for rev_id in panel_expert_ids:
            payload = _build_theory_review_payload(theory, target_kind, dims)
            coros.append(_collect_single_review(
                client, rev_id, system_prompt, payload,
                tid, target_kind, dims,
            ))

    results = await gather_with_limit(coros, max_concurrency=max_concurrency)
    reviews = [r for r in results if r is not None]

    return TheoryPeerReviewSet(
        reviews=reviews,
        reviewer_ids=sorted(set(panel_expert_ids)),
        reviewed_item_ids=[t.get("id", "") for t in theories],
        panel_kind=panel_kind,
    )


async def run_triplet_peer_panel(
    client: LLMClient,
    triplet: dict[str, Any],
    panel_expert_ids: list[str],
    *,
    system_prompt: str = "",
    max_concurrency: int = 6,
) -> list[TripletPeerReview]:
    """Run an external peer panel on a finished triplet.

    Each panelist rates all three variants separately and predicts
    which variant peers will prefer / survive / is underrated.
    """
    dims = TRIPLET_DIMENSIONS
    parent_kernel = triplet.get("parent_kernel", "")

    coros = []
    for rev_id in panel_expert_ids:
        payload = {
            "task": "triplet_peer_review",
            "parent_kernel": parent_kernel,
            "core": triplet.get("core", {}),
            "solid": triplet.get("solid", {}),
            "risky": triplet.get("risky", {}),
            "dimensions_to_rate": dims,
            "instructions": (
                "Rate each variant (core, solid, risky) on every dimension "
                "(1-10). Then predict: which variant will peers prefer? "
                "Which will survive later scrutiny? Which is underrated? "
                "Provide your rationale."
            ),
        }
        coros.append(_collect_triplet_review(
            client, rev_id, system_prompt, payload,
            parent_kernel, dims,
        ))

    results = await gather_with_limit(coros, max_concurrency=max_concurrency)
    return [r for r in results if r is not None]


async def _collect_triplet_review(
    client: LLMClient,
    reviewer_id: str,
    system_prompt: str,
    payload: dict[str, Any],
    parent_kernel: str,
    dimensions: list[str],
) -> TripletPeerReview | None:
    """Collect one triplet peer review."""
    user_message = json.dumps(payload, ensure_ascii=False)
    parsed, record = await client.chat_json(
        agent_id=f"triplet_reviewer_{reviewer_id}_{parent_kernel}",
        system_prompt=system_prompt,
        user_message=user_message,
        expect="object",
    )
    if not record.succeeded or not isinstance(parsed, dict):
        return None

    def _parse_variant_rating(var_data: dict, variant_id: str) -> PeerRating:
        raw_ratings = var_data.get("ratings", {})
        dim_ratings = []
        for dim in dimensions:
            dim_ratings.append(DimensionRating(
                dimension=dim,
                score=_safe_float(raw_ratings.get(dim), 5.0) or 5.0,
            ))
        return PeerRating(
            reviewer_id=reviewer_id,
            target_id=variant_id,
            target_kind="triplet_variant",
            ratings=dim_ratings,
            overall_quality=_safe_float(var_data.get("overall_quality"), 5.0),
            failure_modes=_as_list(var_data.get("failure_modes", [])),
            strengths=_as_list(var_data.get("strengths", [])),
            brief_assessment=str(var_data.get("brief_assessment", "")),
        )

    core_data = parsed.get("core", parsed.get("core_rating", {}))
    solid_data = parsed.get("solid", parsed.get("solid_rating", {}))
    risky_data = parsed.get("risky", parsed.get("risky_rating", {}))

    def _coerce_variant(v: Any) -> str:
        s = str(v).lower().strip()
        if "core" in s:
            return "core"
        if "solid" in s:
            return "solid"
        if "risky" in s:
            return "risky"
        return "core"

    return TripletPeerReview(
        reviewer_id=reviewer_id,
        parent_kernel=parent_kernel,
        core_rating=_parse_variant_rating(
            core_data if isinstance(core_data, dict) else {}, f"{parent_kernel}_core"
        ),
        solid_rating=_parse_variant_rating(
            solid_data if isinstance(solid_data, dict) else {}, f"{parent_kernel}_solid"
        ),
        risky_rating=_parse_variant_rating(
            risky_data if isinstance(risky_data, dict) else {}, f"{parent_kernel}_risky"
        ),
        predicted_preferred_variant=_coerce_variant(
            parsed.get("predicted_preferred_variant", "core")
        ),  # type: ignore[arg-type]
        predicted_surviving_variant=_coerce_variant(
            parsed.get("predicted_surviving_variant", "solid")
        ),  # type: ignore[arg-type]
        predicted_underrated_variant=_coerce_variant(
            parsed.get("predicted_underrated_variant", "risky")
        ),  # type: ignore[arg-type]
        rationale=str(parsed.get("rationale", "")),
    )
