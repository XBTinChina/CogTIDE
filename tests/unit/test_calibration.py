"""Unit tests for cogtide.evaluation.calibration and .forecasting.

Covers the within-run calibration merge, weight extraction, the
false-positive / underrated-winner pattern detectors, and the forecasting
helpers that feed calibration records. Pure computation only.
"""

from __future__ import annotations

from cogtide.evaluation.calibration import (
    compute_calibration_weights,
    identify_false_positive_patterns,
    identify_underrated_winners,
    update_within_run_calibration,
)
from cogtide.evaluation.forecasting import (
    build_calibration_records,
    compute_quality_prediction_errors,
    compute_survival_prediction_accuracy,
)
from cogtide.models.review_signals import (
    IdeaPeerReviewSet,
    PeerPrediction,
    PeerRating,
    PeerReviewEnvelope,
)
from cogtide.models.scorecards import ReviewerCalibrationRecord


def _envelope(reviewer_id, target_id, overall, predicted_avg, survival):
    return PeerReviewEnvelope(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind="idea",
        rating=PeerRating(
            reviewer_id=reviewer_id,
            target_id=target_id,
            target_kind="idea",
            overall_quality=overall,
        ),
        prediction=PeerPrediction(
            reviewer_id=reviewer_id,
            target_id=target_id,
            target_kind="idea",
            predicted_avg_quality=predicted_avg,
            predicted_survival_probability=survival,
        ),
    )


# ---------------------------------------------------------------------------
# calibration.py
# ---------------------------------------------------------------------------


def test_compute_calibration_weights():
    recs = [
        ReviewerCalibrationRecord(reviewer_id="R1", calibration_weight=0.9),
        ReviewerCalibrationRecord(reviewer_id="R2", calibration_weight=0.6),
    ]
    assert compute_calibration_weights(recs) == {"R1": 0.9, "R2": 0.6}


def test_update_within_run_merges_running_averages():
    old = ReviewerCalibrationRecord(
        reviewer_id="R1", run_id="run_old",
        quality_prediction_error=2.0, quality_predictions_made=2,
        survival_prediction_accuracy=0.5, survival_predictions_made=2,
        novelty_bias=0.0,
    )
    new = ReviewerCalibrationRecord(
        reviewer_id="R1", run_id="run_new",
        quality_prediction_error=1.0, quality_predictions_made=2,
        survival_prediction_accuracy=1.0, survival_predictions_made=2,
        novelty_bias=1.0,
    )
    merged = update_within_run_calibration([old], [new])
    assert len(merged) == 1
    m = merged[0]
    assert m.reviewer_id == "R1"
    assert m.run_id == "run_new"
    assert m.quality_prediction_error == 1.5      # (2*2 + 1*2)/4
    assert m.quality_predictions_made == 4
    assert m.survival_prediction_accuracy == 0.75  # (0.5*2 + 1.0*2)/4
    assert m.survival_predictions_made == 4
    assert m.novelty_bias == 0.5                    # (0 + 1)/2
    # quality_cal = 1 - 1.5/5 = 0.7; cal = 0.5*0.7 + 0.5*0.75 = 0.725
    assert m.calibration_score == 0.725
    assert m.calibration_weight == 0.8625           # 0.5 + 0.5*0.725


def test_update_within_run_preserves_and_adds():
    a = ReviewerCalibrationRecord(reviewer_id="R1", calibration_weight=0.8)
    b = ReviewerCalibrationRecord(reviewer_id="R2", calibration_weight=0.7)
    # existing-only reviewer is preserved unchanged
    assert update_within_run_calibration([a], []) == [a]
    # new-only reviewer is added
    assert update_within_run_calibration([], [b]) == [b]


def test_identify_false_positive_patterns():
    fps = identify_false_positive_patterns(
        accepted_ids={"a", "b", "c"},
        high_quality_ids={"a", "b", "x"},
        survived_ids={"b"},
    )
    assert fps == [
        {"item_id": "a", "pattern": "high_quality_but_failed_downstream"}
    ]


def test_identify_underrated_winners():
    winners = identify_underrated_winners(
        underrated_ids={"u1", "u2"},
        survived_ids={"u2", "z"},
    )
    assert winners == [
        {"item_id": "u2", "pattern": "underrated_but_survived"}
    ]


# ---------------------------------------------------------------------------
# forecasting.py
# ---------------------------------------------------------------------------


def _review_set():
    return IdeaPeerReviewSet(
        reviews=[
            _envelope("R1", "I001", overall=8.0, predicted_avg=6.0, survival=0.8),
            _envelope("R2", "I001", overall=6.0, predicted_avg=8.0, survival=0.3),
        ],
        reviewer_ids=["R1", "R2"],
        reviewed_idea_ids=["I001"],
    )


def test_quality_prediction_errors():
    # actual avg quality for I001 = 7.0; each reviewer is off by 1.0
    errs = compute_quality_prediction_errors(_review_set())
    assert errs == {"R1": 1.0, "R2": 1.0}


def test_survival_prediction_accuracy():
    acc = compute_survival_prediction_accuracy(_review_set(), survived_ids={"I001"})
    assert acc == {"R1": 1.0, "R2": 0.0}  # R1 predicted survive (correct), R2 didn't


def test_build_calibration_records():
    recs = build_calibration_records(
        _review_set(), survived_ids={"I001"}, run_id="r"
    )
    by_id = {r.reviewer_id: r for r in recs}
    assert set(by_id) == {"R1", "R2"}
    # R1: q_err 1.0 -> quality_cal 0.8; s_acc 1.0 -> cal 0.9, weight 0.95
    assert by_id["R1"].calibration_score == 0.9
    assert by_id["R1"].calibration_weight == 0.95
    # R2: q_err 1.0 -> quality_cal 0.8; s_acc 0.0 -> cal 0.4, weight 0.7
    assert by_id["R2"].calibration_score == 0.4
    assert by_id["R2"].calibration_weight == 0.7
    assert by_id["R1"].run_id == "r"
