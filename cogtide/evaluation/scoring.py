"""Scorecard computation from raw peer reviews.

Computes the four top-level metrics for every reviewed item:
1. quality_score — mean direct evaluation across dimensions and reviewers.
2. unexpected_support — actual peer support minus expected peer support.
3. survival_forecast — mean predicted survival probability.
4. calibration_weighted_score — quality weighted by reviewer calibration.

The unexpected_support metric is the key peer-prediction signal. It
detects theories that are "more compelling than the community expected"
— exactly the zone where breakthrough candidates live.

``is_underrated`` threshold modes
---------------------------------
``compute_idea_scorecards`` supports two threshold modes:

- ``"adaptive"`` (default): the threshold is the ``underrated_percentile``
  of the *distribution of unexpected_support values in this run*,
  floored at 0. With the default 0.75 this flags roughly the top
  quartile of ideas — relative-to-this-run, not an absolute cutoff.
  LLM reviewers systematically under-predict the crowd (they hedge
  toward conservative midpoints), so the absolute gap is positive on
  most ideas; an adaptive threshold preserves the differentiating
  power of the flag.
- ``"fixed"``: legacy behaviour, flag any idea where
  ``unexpected_support > underrated_threshold`` (default 0.5).

Theory and kernel scorecards are computed one-at-a-time from a single
candidate's external panel, so no distribution is available; those
paths still use the fixed threshold.
"""

from __future__ import annotations

import math
from collections import defaultdict

from cogtide.models.review_signals import (
    IdeaPeerReviewSet,
    PeerReviewEnvelope,
    TripletPeerReview,
)
from cogtide.models.scorecards import (
    DimensionAggregate,
    IdeaScorecard,
    DeepTheoryScorecard,
    KernelScorecard,
    TripletVariantScore,
    TripletScorecard,
)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _compute_dimension_aggregates(
    reviews: list[PeerReviewEnvelope],
    dimensions: list[str],
) -> list[DimensionAggregate]:
    """Aggregate ratings and predictions per dimension across reviewers."""
    aggregates = []
    for dim in dimensions:
        scores = []
        predicted = []
        for rev in reviews:
            for dr in rev.rating.ratings:
                if dr.dimension == dim:
                    scores.append(dr.score)
            for dp in rev.prediction.predicted_dimension_avgs:
                if dp.dimension == dim:
                    predicted.append(dp.score)
        mean_score = _mean(scores)
        mean_pred = _mean(predicted)
        aggregates.append(DimensionAggregate(
            dimension=dim,
            mean_score=round(mean_score, 3),
            std_score=round(_std(scores), 3),
            mean_predicted=round(mean_pred, 3),
            actual_minus_predicted=round(mean_score - mean_pred, 3),
            n_reviews=len(scores),
        ))
    return aggregates


def _quality_score(reviews: list[PeerReviewEnvelope]) -> float:
    """Mean of overall_quality across all reviewers."""
    vals = [r.rating.overall_quality for r in reviews]
    return round(_mean(vals), 3)


def _unexpected_support(reviews: list[PeerReviewEnvelope]) -> float:
    """How much stronger actual support is than reviewers predicted.

    For each reviewer: actual_quality - predicted_avg_quality.
    Then average across reviewers. Positive = surprisingly strong.
    """
    diffs = []
    for r in reviews:
        actual = r.rating.overall_quality
        predicted = r.prediction.predicted_avg_quality
        diffs.append(actual - predicted)
    return round(_mean(diffs), 3)


def _survival_forecast(reviews: list[PeerReviewEnvelope]) -> float:
    """Mean predicted survival probability."""
    vals = [r.prediction.predicted_survival_probability for r in reviews]
    return round(_mean(vals), 3)


def _calibration_weighted_score(
    reviews: list[PeerReviewEnvelope],
    calibration_weights: dict[str, float] | None = None,
) -> float:
    """Quality score weighted by reviewer calibration.

    If calibration_weights is None, falls back to equal weighting.
    """
    if not calibration_weights:
        return _quality_score(reviews)
    total_weight = 0.0
    weighted_sum = 0.0
    for r in reviews:
        w = calibration_weights.get(r.reviewer_id, 1.0)
        weighted_sum += r.rating.overall_quality * w
        total_weight += w
    if total_weight == 0:
        return _quality_score(reviews)
    return round(weighted_sum / total_weight, 3)


def _reviewer_disagreement(reviews: list[PeerReviewEnvelope]) -> float:
    """Standard deviation of overall_quality across reviewers."""
    vals = [r.rating.overall_quality for r in reviews]
    return round(_std(vals), 3)


def _adaptive_underrated_threshold(
    us_values: list[float],
    *,
    percentile: float,
    fallback: float,
    min_sample: int = 4,
) -> float:
    """Compute an adaptive ``is_underrated`` cutoff from a distribution.

    Returns the ``percentile``-th value of ``us_values`` (sorted
    ascending), floored at 0 — an idea with negative unexpected_support
    shouldn't ever be flagged as "underrated". Falls back to the fixed
    threshold when the sample is too small for the quantile to mean
    anything (<4 items by default).
    """
    if len(us_values) < min_sample:
        return fallback
    sorted_vals = sorted(us_values)
    # Exclusive nearest-rank: the smallest value such that `percentile`
    # of the sample is at or below it. With the default 0.75 this flags
    # roughly the top quartile (strict > comparison happens at the call
    # site), including at the minimum sample size of 4.
    idx = max(0, math.ceil(len(sorted_vals) * percentile) - 1)
    return max(0.0, sorted_vals[idx])


def compute_idea_scorecards(
    review_set: IdeaPeerReviewSet,
    *,
    dimensions: list[str] | None = None,
    calibration_weights: dict[str, float] | None = None,
    underrated_mode: str = "adaptive",
    underrated_threshold: float = 0.5,
    underrated_percentile: float = 0.75,
    source_lens_by_id: dict[str, str] | None = None,
) -> list[IdeaScorecard]:
    """Compute scorecards for all reviewed Stage 1 ideas.

    ``is_underrated`` flagging
    --------------------------
    ``underrated_mode="adaptive"`` (default): flag ideas whose
    ``unexpected_support`` exceeds the ``underrated_percentile`` of the
    run's own distribution (floored at 0). With the default 0.75, this
    yields roughly the top quartile of the batch — a relative signal
    that stays meaningful regardless of whether LLM reviewers as a
    group over- or under-predict.

    ``underrated_mode="fixed"``: legacy behaviour, flag ideas with
    ``unexpected_support > underrated_threshold`` (a fixed 0.5 by
    default). Useful for unit tests and for stages where only one item
    is scored at a time.
    """
    if dimensions is None:
        from cogtide.evaluation.peer_review import IDEA_DIMENSIONS
        dimensions = IDEA_DIMENSIONS

    # Group reviews by target_id
    by_idea: dict[str, list[PeerReviewEnvelope]] = defaultdict(list)
    for rev in review_set.reviews:
        by_idea[rev.target_id].append(rev)

    # First pass: compute unexpected_support for every idea that actually
    # received reviews. Ideas with zero reviews are skipped because they
    # would pollute the distribution with meaningless 0.0 values.
    us_by_idea: dict[str, float] = {}
    for idea_id in review_set.reviewed_idea_ids:
        reviews = by_idea.get(idea_id, [])
        if reviews:
            us_by_idea[idea_id] = _unexpected_support(reviews)

    # Choose the effective threshold for is_underrated flagging.
    if underrated_mode == "adaptive":
        effective_threshold = _adaptive_underrated_threshold(
            list(us_by_idea.values()),
            percentile=underrated_percentile,
            fallback=underrated_threshold,
        )
    else:
        effective_threshold = underrated_threshold

    scorecards = []
    for idea_id in review_set.reviewed_idea_ids:
        reviews = by_idea.get(idea_id, [])
        if not reviews:
            scorecards.append(IdeaScorecard(idea_id=idea_id))
            continue

        us = us_by_idea[idea_id]
        scorecards.append(IdeaScorecard(
            idea_id=idea_id,
            source_lens=(source_lens_by_id or {}).get(idea_id, ""),
            quality_score=_quality_score(reviews),
            unexpected_support=us,
            survival_forecast=_survival_forecast(reviews),
            calibration_weighted_score=_calibration_weighted_score(
                reviews, calibration_weights
            ),
            is_underrated=us > effective_threshold,
            reviewer_disagreement=_reviewer_disagreement(reviews),
            dimension_scores=_compute_dimension_aggregates(reviews, dimensions),
            n_reviews=len(reviews),
            reviewer_ids=[r.reviewer_id for r in reviews],
        ))

    return scorecards


def compute_theory_scorecard(
    theory_id: str,
    reviews: list[PeerReviewEnvelope],
    *,
    dimensions: list[str] | None = None,
    calibration_weights: dict[str, float] | None = None,
    underrated_threshold: float = 0.5,
) -> DeepTheoryScorecard:
    """Compute scorecard for one deep theory from external panel reviews."""
    if dimensions is None:
        from cogtide.evaluation.peer_review import THEORY_DIMENSIONS
        dimensions = THEORY_DIMENSIONS

    target_reviews = [r for r in reviews if r.target_id == theory_id]
    if not target_reviews:
        return DeepTheoryScorecard(deep_theory_id=theory_id)

    us = _unexpected_support(target_reviews)
    return DeepTheoryScorecard(
        deep_theory_id=theory_id,
        quality_score=_quality_score(target_reviews),
        unexpected_support=us,
        survival_forecast=_survival_forecast(target_reviews),
        calibration_weighted_score=_calibration_weighted_score(
            target_reviews, calibration_weights
        ),
        is_underrated=us > underrated_threshold,
        reviewer_disagreement=_reviewer_disagreement(target_reviews),
        dimension_scores=_compute_dimension_aggregates(target_reviews, dimensions),
        n_reviews=len(target_reviews),
        reviewer_ids=[r.reviewer_id for r in target_reviews],
    )


def compute_kernel_scorecard(
    kernel_id: str,
    reviews: list[PeerReviewEnvelope],
    *,
    dimensions: list[str] | None = None,
    calibration_weights: dict[str, float] | None = None,
    underrated_threshold: float = 0.5,
) -> KernelScorecard:
    """Compute scorecard for one kernel from external panel reviews."""
    if dimensions is None:
        from cogtide.evaluation.peer_review import THEORY_DIMENSIONS
        dimensions = THEORY_DIMENSIONS

    target_reviews = [r for r in reviews if r.target_id == kernel_id]
    if not target_reviews:
        return KernelScorecard(kernel_id=kernel_id)

    us = _unexpected_support(target_reviews)

    # Check if the panel flags this as only locally persuasive
    underrated_count = sum(
        1 for r in target_reviews
        if r.prediction.overrated_underrated == "overrated"
    )
    locally_persuasive = underrated_count > len(target_reviews) / 2

    return KernelScorecard(
        kernel_id=kernel_id,
        quality_score=_quality_score(target_reviews),
        unexpected_support=us,
        survival_forecast=_survival_forecast(target_reviews),
        calibration_weighted_score=_calibration_weighted_score(
            target_reviews, calibration_weights
        ),
        is_underrated=us > underrated_threshold,
        reviewer_disagreement=_reviewer_disagreement(target_reviews),
        dimension_scores=_compute_dimension_aggregates(target_reviews, dimensions),
        is_locally_persuasive_only=locally_persuasive,
        is_genuinely_deep=not locally_persuasive,
        n_reviews=len(target_reviews),
        reviewer_ids=[r.reviewer_id for r in target_reviews],
    )


def compute_triplet_scorecard(
    parent_kernel: str,
    triplet_reviews: list[TripletPeerReview],
    theory_ids: dict[str, str] | None = None,
) -> TripletScorecard:
    """Compute scorecard for a triplet from external panel reviews.

    Applies operational definitions:
    - Core = highest balanced score across quality dimensions.
    - Solid = highest robustness/defensibility above minimum novelty.
    - Risky = highest breakthrough-potential above minimum coherence.

    Args:
        parent_kernel: kernel ID this triplet elaborates.
        triplet_reviews: reviews from the external panel.
        theory_ids: mapping of role -> theory_id, e.g.
            {"core": "T01", "solid": "T02", "risky": "T03"}.
    """
    if theory_ids is None:
        theory_ids = {"core": f"{parent_kernel}_core",
                      "solid": f"{parent_kernel}_solid",
                      "risky": f"{parent_kernel}_risky"}

    variant_scores: dict[str, TripletVariantScore] = {}

    for role in ("core", "solid", "risky"):
        tid = theory_ids.get(role, f"{parent_kernel}_{role}")
        ratings_attr = f"{role}_rating"

        # Collect dimension scores across all reviewers
        dim_scores: dict[str, list[float]] = defaultdict(list)
        for rev in triplet_reviews:
            rating = getattr(rev, ratings_attr, None)
            if rating is None:
                continue
            for dr in rating.ratings:
                dim_scores[dr.dimension].append(dr.score)

        # Compute mean per dimension
        coherence = _mean(dim_scores.get("coherence", []))
        defensibility = _mean(dim_scores.get("defensibility", []))
        novelty = _mean(dim_scores.get("novelty", []))
        distinctiveness = _mean(dim_scores.get("distinctiveness", []))
        fertility = _mean(dim_scores.get("experimental_fertility", []))
        upside = _mean(dim_scores.get("upside_if_true", []))

        all_dims = [coherence, defensibility, novelty, distinctiveness, fertility, upside]
        balanced = _mean([d for d in all_dims if d > 0])
        robustness = _mean([defensibility, coherence]) if defensibility > 0 else 0.0
        breakthrough = _mean([novelty, upside]) if novelty > 0 else 0.0

        # Peer predictions about this variant
        pref_count = sum(1 for r in triplet_reviews if r.predicted_preferred_variant == role)
        surv_count = sum(1 for r in triplet_reviews if r.predicted_surviving_variant == role)
        under_count = sum(1 for r in triplet_reviews if r.predicted_underrated_variant == role)
        n = len(triplet_reviews) or 1

        variant_scores[role] = TripletVariantScore(
            variant_role=role,
            theory_id=tid,
            coherence=round(coherence, 3),
            defensibility=round(defensibility, 3),
            novelty=round(novelty, 3),
            distinctiveness=round(distinctiveness, 3),
            experimental_fertility=round(fertility, 3),
            upside_if_true=round(upside, 3),
            balanced_score=round(balanced, 3),
            robustness_score=round(robustness, 3),
            breakthrough_potential=round(breakthrough, 3),
            predicted_peer_preference_fraction=round(pref_count / n, 3),
            predicted_survival_fraction=round(surv_count / n, 3),
            predicted_underrated_fraction=round(under_count / n, 3),
        )

    # Apply operational definitions to assign roles
    vs_list = list(variant_scores.values())

    # Core = highest balanced score
    core_pick = max(vs_list, key=lambda v: v.balanced_score)
    # Solid = highest robustness above minimum novelty (3.0)
    solid_candidates = [v for v in vs_list if v.novelty >= 3.0]
    if not solid_candidates:
        solid_candidates = vs_list
    solid_pick = max(solid_candidates, key=lambda v: v.robustness_score)
    # Risky = highest breakthrough potential above minimum coherence (3.0)
    risky_candidates = [v for v in vs_list if v.coherence >= 3.0]
    if not risky_candidates:
        risky_candidates = vs_list
    risky_pick = max(risky_candidates, key=lambda v: v.breakthrough_potential)

    # Check if assignments differ from original labels
    original_core = theory_ids.get("core", "")
    original_solid = theory_ids.get("solid", "")
    original_risky = theory_ids.get("risky", "")

    reassigned = (
        core_pick.theory_id != original_core
        or solid_pick.theory_id != original_solid
        or risky_pick.theory_id != original_risky
    )

    rationale = ""
    if reassigned:
        rationale = (
            f"Roles reassigned based on peer scores: "
            f"core={core_pick.theory_id} (balanced={core_pick.balanced_score}), "
            f"solid={solid_pick.theory_id} (robustness={solid_pick.robustness_score}), "
            f"risky={risky_pick.theory_id} (breakthrough={risky_pick.breakthrough_potential})"
        )

    return TripletScorecard(
        parent_kernel=parent_kernel,
        variant_scores=vs_list,
        assigned_core_id=core_pick.theory_id,
        assigned_solid_id=solid_pick.theory_id,
        assigned_risky_id=risky_pick.theory_id,
        roles_reassigned=reassigned,
        reassignment_rationale=rationale,
        n_reviews=len(triplet_reviews),
        reviewer_ids=sorted({r.reviewer_id for r in triplet_reviews}),
    )
