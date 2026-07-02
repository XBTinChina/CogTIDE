"""Calibration tracking and updating.

Manages within-run and across-run calibration of reviewer predictions.

Within-run learning:
  As Stages 2 and 3 unfold, update reviewer calibration based on
  whether predicted peer ratings match actual peer ratings and
  whether survival forecasts match actual later outcomes. Used
  lightly within a run.

Across-run learning:
  When the memory compiler runs after Stage 4, summarize which
  reviewer roles were calibrated, which theory patterns were false
  positives, which preservation tags mattered, and which underrated
  signals predicted later strength.
"""

from __future__ import annotations

from typing import Any

from cogtide.models.scorecards import ReviewerCalibrationRecord


def update_within_run_calibration(
    existing_records: list[ReviewerCalibrationRecord],
    new_records: list[ReviewerCalibrationRecord],
) -> list[ReviewerCalibrationRecord]:
    """Merge new calibration observations into existing records.

    For reviewers seen in both lists, running averages are updated.
    For reviewers seen only in new_records, they are added.
    Existing-only reviewers are preserved unchanged.
    """
    existing_by_id: dict[str, ReviewerCalibrationRecord] = {
        r.reviewer_id: r for r in existing_records
    }
    new_by_id: dict[str, ReviewerCalibrationRecord] = {
        r.reviewer_id: r for r in new_records
    }

    merged: list[ReviewerCalibrationRecord] = []

    all_ids = sorted(set(existing_by_id) | set(new_by_id))
    for rid in all_ids:
        old = existing_by_id.get(rid)
        new = new_by_id.get(rid)

        if old is None and new is not None:
            merged.append(new)
            continue
        if new is None and old is not None:
            merged.append(old)
            continue

        # Both exist — compute running averages
        assert old is not None and new is not None
        total_q = old.quality_predictions_made + new.quality_predictions_made
        total_s = old.survival_predictions_made + new.survival_predictions_made

        if total_q > 0:
            combined_q_err = (
                old.quality_prediction_error * old.quality_predictions_made
                + new.quality_prediction_error * new.quality_predictions_made
            ) / total_q
        else:
            combined_q_err = 0.0

        if total_s > 0:
            combined_s_acc = (
                old.survival_prediction_accuracy * old.survival_predictions_made
                + new.survival_prediction_accuracy * new.survival_predictions_made
            ) / total_s
        else:
            combined_s_acc = 0.5

        # Combine novelty bias as running average
        combined_n_bias = (old.novelty_bias + new.novelty_bias) / 2.0

        # Recompute calibration score
        quality_cal = max(0.0, 1.0 - combined_q_err / 5.0)
        cal_score = 0.5 * quality_cal + 0.5 * combined_s_acc
        cal_weight = 0.5 + 0.5 * cal_score

        merged.append(ReviewerCalibrationRecord(
            reviewer_id=rid,
            run_id=new.run_id or old.run_id,
            quality_prediction_error=round(combined_q_err, 4),
            quality_predictions_made=total_q,
            survival_prediction_accuracy=round(combined_s_acc, 4),
            survival_predictions_made=total_s,
            novelty_bias=round(combined_n_bias, 4),
            overrates_elegance=old.overrates_elegance or new.overrates_elegance,
            underrates_risk_takers=(
                old.underrates_risk_takers or new.underrates_risk_takers
            ),
            calibration_score=round(cal_score, 4),
            calibration_weight=round(cal_weight, 4),
        ))

    return merged


def compute_calibration_weights(
    records: list[ReviewerCalibrationRecord],
) -> dict[str, float]:
    """Extract calibration weights as a simple {reviewer_id: weight} dict.

    This is the format consumed by the scoring functions.
    """
    return {r.reviewer_id: r.calibration_weight for r in records}


def summarize_calibration_for_memory(
    records: list[ReviewerCalibrationRecord],
) -> dict[str, Any]:
    """Produce a memory-friendly summary of reviewer calibration.

    Used by the memory compiler to persist calibration insights
    across runs.
    """
    if not records:
        return {"reviewer_count": 0, "summaries": []}

    summaries = []
    for r in sorted(records, key=lambda x: x.calibration_score, reverse=True):
        summary: dict[str, Any] = {
            "reviewer_id": r.reviewer_id,
            "calibration_score": r.calibration_score,
            "quality_prediction_error": r.quality_prediction_error,
            "survival_accuracy": r.survival_prediction_accuracy,
        }
        # Note bias patterns
        biases = []
        if abs(r.novelty_bias) > 0.5:
            direction = "overestimates" if r.novelty_bias > 0 else "underestimates"
            biases.append(f"{direction} novelty (bias={r.novelty_bias:.2f})")
        if r.overrates_elegance:
            biases.append("overrates elegance")
        if r.underrates_risk_takers:
            biases.append("underrates risk-takers")
        if biases:
            summary["bias_patterns"] = biases
        summaries.append(summary)

    # Aggregate stats
    cal_scores = [r.calibration_score for r in records]
    mean_cal = sum(cal_scores) / len(cal_scores)
    best = max(records, key=lambda r: r.calibration_score)
    worst = min(records, key=lambda r: r.calibration_score)

    return {
        "reviewer_count": len(records),
        "mean_calibration": round(mean_cal, 4),
        "best_calibrated": best.reviewer_id,
        "worst_calibrated": worst.reviewer_id,
        "summaries": summaries,
    }


def identify_false_positive_patterns(
    accepted_ids: set[str],
    high_quality_ids: set[str],
    survived_ids: set[str],
) -> list[dict[str, Any]]:
    """Identify items that looked strong but failed downstream.

    A false positive is an item that:
    - was accepted (passed the gate), AND
    - had high quality scores, BUT
    - did NOT survive to the next stage.

    Returns a list of pattern records for memory.
    """
    false_positives = accepted_ids & high_quality_ids - survived_ids
    return [
        {"item_id": iid, "pattern": "high_quality_but_failed_downstream"}
        for iid in sorted(false_positives)
    ]


def identify_underrated_winners(
    underrated_ids: set[str],
    survived_ids: set[str],
) -> list[dict[str, Any]]:
    """Identify items that were underrated but survived anyway.

    An underrated winner had:
    - modest initial quality scores,
    - high unexpected support (rated better than predicted),
    - AND survived downstream.

    Returns a list of pattern records for memory.
    """
    winners = underrated_ids & survived_ids
    return [
        {"item_id": iid, "pattern": "underrated_but_survived"}
        for iid in sorted(winners)
    ]
