"""Forecast collection and outcome comparison.

Manages the collection of peer forecasts (what do you think others
will think?) and compares them against actual outcomes to measure
reviewer calibration.

This module bridges the gap between the raw peer-prediction signals
collected in peer_review.py and the calibration tracking in
calibration.py.
"""

from __future__ import annotations

from collections import defaultdict

from cogtide.models.review_signals import (
    PeerReviewEnvelope,
    IdeaPeerReviewSet,
    TheoryPeerReviewSet,
)
from cogtide.models.scorecards import ReviewerCalibrationRecord


def compute_quality_prediction_errors(
    review_set: IdeaPeerReviewSet | TheoryPeerReviewSet,
) -> dict[str, float]:
    """For each reviewer, compute MAE between their predicted_avg_quality
    and the actual average quality given by all reviewers to each item.

    Returns: {reviewer_id: mean_absolute_error}.
    """
    # First compute actual average quality per item
    by_item: dict[str, list[float]] = defaultdict(list)
    for rev in review_set.reviews:
        by_item[rev.target_id].append(rev.rating.overall_quality)

    actual_avg: dict[str, float] = {
        tid: sum(vals) / len(vals) for tid, vals in by_item.items() if vals
    }

    # Then compute per-reviewer prediction error
    reviewer_errors: dict[str, list[float]] = defaultdict(list)
    for rev in review_set.reviews:
        actual = actual_avg.get(rev.target_id)
        if actual is not None:
            error = abs(rev.prediction.predicted_avg_quality - actual)
            reviewer_errors[rev.reviewer_id].append(error)

    return {
        rid: sum(errs) / len(errs)
        for rid, errs in reviewer_errors.items()
        if errs
    }


def compute_survival_prediction_accuracy(
    review_set: IdeaPeerReviewSet | TheoryPeerReviewSet,
    survived_ids: set[str],
) -> dict[str, float]:
    """For each reviewer, compute accuracy of survival predictions.

    A prediction is "correct" if:
    - predicted_survival_probability >= 0.5 AND item survived, or
    - predicted_survival_probability < 0.5 AND item did NOT survive.

    Args:
        review_set: the reviews to evaluate.
        survived_ids: set of item IDs that actually survived the next stage.

    Returns: {reviewer_id: accuracy_fraction}.
    """
    reviewer_correct: dict[str, list[bool]] = defaultdict(list)
    for rev in review_set.reviews:
        predicted_survive = rev.prediction.predicted_survival_probability >= 0.5
        actually_survived = rev.target_id in survived_ids
        reviewer_correct[rev.reviewer_id].append(
            predicted_survive == actually_survived
        )

    return {
        rid: sum(correct) / len(correct)
        for rid, correct in reviewer_correct.items()
        if correct
    }


def compute_dimension_bias(
    review_set: IdeaPeerReviewSet | TheoryPeerReviewSet,
    dimension: str,
) -> dict[str, float]:
    """For each reviewer, compute their bias on a specific dimension.

    Bias = reviewer's mean score on dimension - actual mean across all
    reviewers for the same items. Positive = consistently overestimates.

    Returns: {reviewer_id: bias}.
    """
    # Actual mean per item on this dimension
    by_item: dict[str, list[float]] = defaultdict(list)
    for rev in review_set.reviews:
        for dr in rev.rating.ratings:
            if dr.dimension == dimension:
                by_item[rev.target_id].append(dr.score)

    actual_mean: dict[str, float] = {
        tid: sum(vals) / len(vals) for tid, vals in by_item.items() if vals
    }

    # Per-reviewer bias
    reviewer_diffs: dict[str, list[float]] = defaultdict(list)
    for rev in review_set.reviews:
        for dr in rev.rating.ratings:
            if dr.dimension == dimension:
                item_mean = actual_mean.get(rev.target_id)
                if item_mean is not None:
                    reviewer_diffs[rev.reviewer_id].append(dr.score - item_mean)

    return {
        rid: sum(diffs) / len(diffs)
        for rid, diffs in reviewer_diffs.items()
        if diffs
    }


def build_calibration_records(
    review_set: IdeaPeerReviewSet | TheoryPeerReviewSet,
    survived_ids: set[str],
    run_id: str = "",
) -> list[ReviewerCalibrationRecord]:
    """Build calibration records for all reviewers in a review set.

    Combines quality prediction errors, survival prediction accuracy,
    and dimension biases into a single calibration record per reviewer.
    """
    quality_errors = compute_quality_prediction_errors(review_set)
    survival_accuracy = compute_survival_prediction_accuracy(
        review_set, survived_ids
    )
    novelty_bias = compute_dimension_bias(review_set, "novelty")

    # Count predictions per reviewer
    prediction_counts: dict[str, int] = defaultdict(int)
    survival_counts: dict[str, int] = defaultdict(int)
    for rev in review_set.reviews:
        prediction_counts[rev.reviewer_id] += 1
        survival_counts[rev.reviewer_id] += 1

    all_reviewer_ids = set(quality_errors) | set(survival_accuracy)
    records = []
    for rid in sorted(all_reviewer_ids):
        q_err = quality_errors.get(rid, 0.0)
        s_acc = survival_accuracy.get(rid, 0.5)
        n_bias = novelty_bias.get(rid, 0.0)

        # Calibration score: combine quality prediction accuracy and
        # survival prediction accuracy. Lower error = higher calibration.
        # Scale quality error (typically 0-5) to 0-1 range.
        quality_cal = max(0.0, 1.0 - q_err / 5.0)
        cal_score = 0.5 * quality_cal + 0.5 * s_acc

        # Weight is a softened version of calibration score
        # to avoid completely zeroing out poorly calibrated reviewers
        cal_weight = 0.5 + 0.5 * cal_score

        records.append(ReviewerCalibrationRecord(
            reviewer_id=rid,
            run_id=run_id,
            quality_prediction_error=round(q_err, 4),
            quality_predictions_made=prediction_counts.get(rid, 0),
            survival_prediction_accuracy=round(s_acc, 4),
            survival_predictions_made=survival_counts.get(rid, 0),
            novelty_bias=round(n_bias, 4),
            overrates_elegance=False,  # computed from cross-run data
            underrates_risk_takers=n_bias < -1.0,
            calibration_score=round(cal_score, 4),
            calibration_weight=round(cal_weight, 4),
        ))

    return records
