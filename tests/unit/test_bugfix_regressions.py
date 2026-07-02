"""Regression tests for bugs found in the pre-release review.

Each test pins the corrected behavior of a specific defect so it cannot
silently reappear. All tests are network-free.
"""

from __future__ import annotations

import subprocess
import sys

from cogtide.evaluation.peer_review import (
    IDEA_DIMENSIONS,
    _parse_review_response,
    _safe_float,
    _select_reviewers,
)
from cogtide.evaluation.scoring import _adaptive_underrated_threshold
from cogtide.memory.policy import _filter_policy
from cogtide.registry import AgentRegistry
from cogtide.utils.ids import stable_hash


# ── configs/agents.yaml `extra:` blocks must reach the stages ─────────────

def test_registry_merges_explicit_extra_mapping():
    """`extra` is a dataclass field name, so the unknown-key sweep alone
    drops the explicit `extra: {expert_index, domain}` mappings that the
    Stage 1 experts rely on for their source_lens domains."""
    reg = AgentRegistry.load()
    e1 = reg.get("S01_expert_01")
    assert e1.extra.get("domain") == "reinforcement_learning"
    assert e1.extra.get("expert_index") == 1

    experts = reg.for_substage("stage_01", "S01.03")
    domains = {a.extra.get("domain") for a in experts}
    assert len(domains) == 19
    assert None not in domains


# ── reviewer assignment must be stable across interpreter runs ────────────

def test_reviewer_selection_survives_hash_randomization():
    """Seeding with built-in hash() made panels differ per process
    (PYTHONHASHSEED); stable_hash keeps assignment reproducible."""
    snippet = (
        "from cogtide.evaluation.peer_review import _select_reviewers;"
        "from cogtide.utils.ids import stable_hash;"
        "print(_select_reviewers([f'e{i}' for i in range(19)], {'e3'}, 5,"
        " seed=42 + stable_hash('I007') % 10000))"
    )
    outputs = set()
    for hash_seed in ("0", "1", "2"):
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": hash_seed},
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1


def test_select_reviewers_excludes_author():
    pool = [f"e{i}" for i in range(10)]
    chosen = _select_reviewers(pool, {"e2"}, 5, seed=1)
    assert "e2" not in chosen
    assert len(chosen) == 5


# ── malformed LLM review output must not crash the batch ──────────────────

def test_safe_float_junk_tolerance():
    assert _safe_float(None, 5.0) == 5.0
    assert _safe_float({"score": 7}, 5.0) == 7.0
    assert _safe_float({"unexpected": 1}, 5.0) == 5.0
    assert _safe_float("not-a-number", 5.0) == 5.0
    assert _safe_float("7.5", 5.0) == 7.5
    assert _safe_float(0, 5.0) == 0.0


def test_parse_review_response_survives_malformed_payload():
    """null / nested-object / string values in numeric fields previously
    raised TypeError and aborted the whole asyncio.gather sweep."""
    raw = {
        "ratings": {
            "novelty": None,
            "coherence": {"score": 8},
            "testability": "strong",
        },
        "overall_quality": {"nested": True},
        "predictions": {
            "predicted_avg_quality": None,
            "predicted_survival_probability": "high",
        },
    }
    env = _parse_review_response(raw, "rev1", "I001", "idea", IDEA_DIMENSIONS)
    assert env.rating.overall_quality == 5.0
    assert env.prediction.predicted_avg_quality == 5.0
    assert env.prediction.predicted_survival_probability == 0.5
    by_dim = {r.dimension: r.score for r in env.rating.ratings}
    assert by_dim["novelty"] == 5.0
    assert by_dim["coherence"] == 8.0
    assert by_dim["testability"] == 5.0


# ── adaptive underrated threshold must flag at the minimum sample ─────────

def test_adaptive_threshold_flags_at_min_sample():
    """The old inclusive index made the threshold the sample max at n=4,
    so nothing could ever be flagged at the documented minimum sample."""
    vals = [0.1, 0.2, 0.3, 0.4]
    threshold = _adaptive_underrated_threshold(
        vals, percentile=0.75, fallback=0.5,
    )
    flagged = [v for v in vals if v > threshold]
    assert flagged == [0.4]


def test_adaptive_threshold_top_quartile_at_n8():
    vals = [0.1 * i for i in range(1, 9)]
    threshold = _adaptive_underrated_threshold(
        vals, percentile=0.75, fallback=0.5,
    )
    assert sum(1 for v in vals if v > threshold) == 2


def test_adaptive_threshold_small_sample_falls_back():
    assert _adaptive_underrated_threshold(
        [0.1, 0.2, 0.3], percentile=0.75, fallback=0.5,
    ) == 0.5


# ── malformed learned-policy overlays must not brick the config ───────────

def test_filter_policy_drops_non_dict_stages():
    """A null/list `stages:` in memory/learned/active/policy.yaml used to
    pass through and REPLACE the entire stages config on deep-merge."""
    assert _filter_policy({"stages": None}) == {}
    assert _filter_policy({"stages": ["stage_02"]}) == {}
    assert _filter_policy({"stages": "oops"}) == {}


def test_filter_policy_allowlists_stage_keys():
    overlay = {
        "stages": {
            "stage_03": {"target_kernel_count": 7, "arbitrary_injection": 1},
            "stage_02": "malformed",
        },
        "not_allowed_top_level": {"x": 1},
    }
    assert _filter_policy(overlay) == {
        "stages": {"stage_03": {"target_kernel_count": 7}},
    }


# ── stable_hash is actually stable ─────────────────────────────────────────

def test_stable_hash_is_deterministic_and_32bit():
    assert stable_hash("I007") == stable_hash("I007")
    assert 0 <= stable_hash("anything") < 2**32


# ── Stage-2 panel survival forecasts scored against Stage-3 outcomes ──────

def test_apply_survival_outcome_update_touches_only_survival():
    from cogtide.evaluation.forecasting import apply_survival_outcome_update
    from cogtide.models.review_signals import (
        PeerPrediction,
        PeerRating,
        PeerReviewEnvelope,
        TheoryPeerReviewSet,
    )
    from cogtide.models.scorecards import ReviewerCalibrationRecord

    def _env(reviewer, target, survival_prob):
        return PeerReviewEnvelope(
            reviewer_id=reviewer,
            target_id=target,
            target_kind="deep_theory",
            rating=PeerRating(
                reviewer_id=reviewer,
                target_id=target,
                target_kind="deep_theory",
                overall_quality=6.0,
            ),
            prediction=PeerPrediction(
                reviewer_id=reviewer,
                target_id=target,
                target_kind="deep_theory",
                predicted_avg_quality=6.0,
                predicted_survival_probability=survival_prob,
            ),
        )

    # rev_a predicted D01 survives (0.9) and D02 dies (0.1);
    # only D01 actually contributed to a kernel → 2/2 correct.
    review_set = TheoryPeerReviewSet(
        reviews=[_env("rev_a", "D01", 0.9), _env("rev_a", "D02", 0.1)],
        reviewer_ids=["rev_a"],
        reviewed_item_ids=["D01", "D02"],
        panel_kind="stage2_external",
    )
    existing = [
        ReviewerCalibrationRecord(
            reviewer_id="rev_a",
            quality_prediction_error=1.0,
            quality_predictions_made=2,
            survival_prediction_accuracy=0.5,
            survival_predictions_made=2,
        ),
        ReviewerCalibrationRecord(reviewer_id="rev_b"),
    ]
    updated = apply_survival_outcome_update(existing, review_set, {"D01"})
    by_id = {r.reviewer_id: r for r in updated}

    a = by_id["rev_a"]
    # Survival: count-weighted merge of (0.5 over 2) and (1.0 over 2) = 0.75
    assert a.survival_prediction_accuracy == 0.75
    assert a.survival_predictions_made == 4
    # Quality side untouched
    assert a.quality_prediction_error == 1.0
    assert a.quality_predictions_made == 2
    # Score/weight recomputed: 0.5*(1-1/5) + 0.5*0.75 = 0.775
    assert a.calibration_score == 0.775
    assert a.calibration_weight == 0.5 + 0.5 * 0.775
    # Uninvolved reviewer untouched
    assert by_id["rev_b"] == existing[1]
