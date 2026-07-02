"""Peer-prediction evaluation engine.

Provides blind peer review orchestration, forecast collection,
scorecard computation, and calibration tracking for Stages 2-4.
"""

from .peer_review import (
    run_idea_peer_review,
    run_theory_peer_panel,
    run_triplet_peer_panel,
)
from .scoring import (
    compute_idea_scorecards,
    compute_theory_scorecard,
    compute_kernel_scorecard,
    compute_triplet_scorecard,
)
from .calibration import (
    update_within_run_calibration,
    compute_calibration_weights,
)

__all__ = [
    "run_idea_peer_review",
    "run_theory_peer_panel",
    "run_triplet_peer_panel",
    "compute_idea_scorecards",
    "compute_theory_scorecard",
    "compute_kernel_scorecard",
    "compute_triplet_scorecard",
    "update_within_run_calibration",
    "compute_calibration_weights",
]
