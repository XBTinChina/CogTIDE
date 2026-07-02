"""Unit tests for cogtide.evaluation.scoring.

Builds minimal peer-review envelopes and checks the four scorecard
signals (quality_score, unexpected_support, survival_forecast,
calibration_weighted_score) plus derived flags. Pure computation only.
"""

from __future__ import annotations

from cogtide.evaluation.scoring import (
    compute_idea_scorecards,
    compute_theory_scorecard,
)
from cogtide.models.review_signals import (
    DimensionRating,
    IdeaPeerReviewSet,
    PeerPrediction,
    PeerRating,
    PeerReviewEnvelope,
)


def _envelope(
    reviewer_id: str,
    target_id: str,
    *,
    target_kind: str = "deep_theory",
    overall: float,
    predicted_avg: float,
    survival: float,
    dim_ratings: list[tuple[str, float]] | None = None,
    predicted_dims: list[tuple[str, float]] | None = None,
) -> PeerReviewEnvelope:
    ratings = [DimensionRating(dimension=d, score=s) for d, s in (dim_ratings or [])]
    preds = [DimensionRating(dimension=d, score=s) for d, s in (predicted_dims or [])]
    rating = PeerRating(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind=target_kind,
        ratings=ratings,
        overall_quality=overall,
    )
    prediction = PeerPrediction(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind=target_kind,
        predicted_avg_quality=predicted_avg,
        predicted_dimension_avgs=preds,
        predicted_survival_probability=survival,
    )
    return PeerReviewEnvelope(
        reviewer_id=reviewer_id,
        target_id=target_id,
        target_kind=target_kind,
        rating=rating,
        prediction=prediction,
    )


def test_theory_scorecard_core_signals():
    reviews = [
        _envelope(
            "R1", "D01", overall=8.0, predicted_avg=6.0, survival=0.8,
            dim_ratings=[("novelty", 8.0), ("coherence", 7.0)],
            predicted_dims=[("novelty", 6.0)],
        ),
        _envelope(
            "R2", "D01", overall=6.0, predicted_avg=5.0, survival=0.6,
            dim_ratings=[("novelty", 6.0), ("coherence", 5.0)],
        ),
    ]
    sc = compute_theory_scorecard("D01", reviews, dimensions=["novelty", "coherence"])

    assert sc.deep_theory_id == "D01"
    assert sc.quality_score == 7.0                 # mean(8, 6)
    assert sc.unexpected_support == 1.5            # mean(8-6, 6-5)
    assert sc.survival_forecast == 0.7             # mean(0.8, 0.6)
    assert sc.is_underrated is True                # 1.5 > 0.5 (fixed threshold)
    assert sc.reviewer_disagreement == 1.414       # sample std of [8, 6]
    assert sc.n_reviews == 2
    assert sorted(sc.reviewer_ids) == ["R1", "R2"]

    by_dim = {a.dimension: a for a in sc.dimension_scores}
    assert set(by_dim) == {"novelty", "coherence"}
    assert by_dim["novelty"].mean_score == 7.0
    assert by_dim["novelty"].mean_predicted == 6.0
    assert by_dim["novelty"].actual_minus_predicted == 1.0


def test_theory_scorecard_calibration_weighting():
    reviews = [
        _envelope("R1", "D01", overall=8.0, predicted_avg=6.0, survival=0.5),
        _envelope("R2", "D01", overall=6.0, predicted_avg=6.0, survival=0.5),
    ]
    # Equal weighting falls back to plain quality mean.
    unweighted = compute_theory_scorecard("D01", reviews, dimensions=[])
    assert unweighted.calibration_weighted_score == 7.0

    weighted = compute_theory_scorecard(
        "D01", reviews, dimensions=[], calibration_weights={"R1": 2.0, "R2": 1.0}
    )
    # (8*2 + 6*1) / 3 = 7.333
    assert weighted.calibration_weighted_score == 7.333


def test_theory_scorecard_no_reviews_is_empty():
    sc = compute_theory_scorecard("D99", [], dimensions=[])
    assert sc.deep_theory_id == "D99"
    assert sc.quality_score == 0.0
    assert sc.n_reviews == 0


def test_idea_scorecards_fixed_mode():
    reviews = [
        _envelope("R1", "I001", target_kind="idea", overall=8.0,
                  predicted_avg=6.0, survival=0.9),
        _envelope("R2", "I001", target_kind="idea", overall=8.0,
                  predicted_avg=6.0, survival=0.9),
        _envelope("R1", "I002", target_kind="idea", overall=5.0,
                  predicted_avg=5.0, survival=0.4),
    ]
    review_set = IdeaPeerReviewSet(
        reviews=reviews,
        reviewer_ids=["R1", "R2"],
        reviewed_idea_ids=["I001", "I002", "I003"],  # I003 has no reviews
    )
    cards = compute_idea_scorecards(
        review_set,
        dimensions=[],
        underrated_mode="fixed",
        underrated_threshold=0.5,
    )
    by_id = {c.idea_id: c for c in cards}

    assert set(by_id) == {"I001", "I002", "I003"}
    assert by_id["I001"].quality_score == 8.0
    assert by_id["I001"].unexpected_support == 2.0
    assert by_id["I001"].is_underrated is True     # 2.0 > 0.5
    assert by_id["I002"].unexpected_support == 0.0
    assert by_id["I002"].is_underrated is False    # 0.0 not > 0.5
    # Idea with no reviews gets a bare default scorecard.
    assert by_id["I003"].n_reviews == 0
    assert by_id["I003"].quality_score == 0.0
