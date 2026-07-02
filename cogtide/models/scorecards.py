"""Scorecard models: aggregated peer-prediction signals for promotion decisions.

Every important promotion decision in v2 uses these scorecards.
A scorecard aggregates blind peer ratings, peer forecasts, and
calibration-aware weighting into four top-level metrics:

1. quality_score — average direct evaluation across dimensions.
2. unexpected_support — how much stronger actual peer support was
   than reviewers expected (the key peer-prediction signal).
3. survival_forecast — average predicted probability the item
   survives the next stage.
4. calibration_weighted_score — quality score weighted by how
   well each reviewer's past forecasts matched later outcomes.

Scorecards exist at every promotion boundary:
- IdeaScorecard: Stage 1 → Stage 2 (idea screening)
- DeepTheoryScorecard: Stage 2 external panel
- KernelScorecard: Stage 3 external panel
- TripletScorecard: Stage 4 finalization
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DimensionAggregate(BaseModel):
    """Aggregated score for one quality dimension across all reviewers."""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    mean_score: float = 0.0
    std_score: float = 0.0
    mean_predicted: float = 0.0  # what reviewers predicted others would give
    actual_minus_predicted: float = 0.0  # surprise signal
    n_reviews: int = 0


class IdeaScorecard(BaseModel):
    """Scorecard for one Stage 1 idea, computed from blind peer reviews.

    Used by the Stage 2 coalition selector to rank and select ideas.
    """

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    source_lens: str = ""  # expert who generated it

    # Top-level metrics
    quality_score: float = 0.0
    unexpected_support: float = 0.0
    survival_forecast: float = 0.0
    calibration_weighted_score: float = 0.0

    # Derived flags
    is_underrated: bool = False  # unexpected_support > threshold
    reviewer_disagreement: float = 0.0  # std of overall_quality across reviewers
    diversity_contribution: float = 0.0  # how different from other high-scorers

    # Dimension breakdowns
    dimension_scores: list[DimensionAggregate] = Field(default_factory=list)

    # Audit
    n_reviews: int = 0
    reviewer_ids: list[str] = Field(default_factory=list)


class DeepTheoryScorecard(BaseModel):
    """Scorecard for one Stage 2 deep theory from the external peer panel.

    The synthesis_judge reads this alongside the candidate theory and
    traceability record when making the acceptance decision.
    """

    model_config = ConfigDict(extra="forbid")

    deep_theory_id: str

    # Top-level metrics
    quality_score: float = 0.0
    unexpected_support: float = 0.0
    survival_forecast: float = 0.0
    calibration_weighted_score: float = 0.0

    # Derived flags
    is_underrated: bool = False
    reviewer_disagreement: float = 0.0

    # Per-dimension breakdown
    dimension_scores: list[DimensionAggregate] = Field(default_factory=list)

    # Audit
    n_reviews: int = 0
    reviewer_ids: list[str] = Field(default_factory=list)
    panel_kind: str = "stage2_external"


class KernelScorecard(BaseModel):
    """Scorecard for one Stage 3 kernel from the external peer panel.

    The kernel_judge reads this alongside the candidate kernel when
    deciding acceptance.
    """

    model_config = ConfigDict(extra="forbid")

    kernel_id: str

    # Top-level metrics
    quality_score: float = 0.0
    unexpected_support: float = 0.0
    survival_forecast: float = 0.0
    calibration_weighted_score: float = 0.0

    # Derived flags
    is_underrated: bool = False
    reviewer_disagreement: float = 0.0

    # Per-dimension breakdown
    dimension_scores: list[DimensionAggregate] = Field(default_factory=list)

    # External panel judgments
    is_locally_persuasive_only: bool = False  # flag from panel
    is_genuinely_deep: bool = True  # flag from panel

    # Audit
    n_reviews: int = 0
    reviewer_ids: list[str] = Field(default_factory=list)
    panel_kind: str = "stage3_external"


class TripletVariantScore(BaseModel):
    """Scores for one variant (core/solid/risky) within a triplet."""

    model_config = ConfigDict(extra="forbid")

    variant_role: str  # "core", "solid", "risky"
    theory_id: str

    # Quality dimensions rated by external panel
    coherence: float = 0.0
    defensibility: float = 0.0
    novelty: float = 0.0
    distinctiveness: float = 0.0
    experimental_fertility: float = 0.0
    upside_if_true: float = 0.0

    # Aggregate
    balanced_score: float = 0.0  # mean of all dimensions
    robustness_score: float = 0.0  # defensibility-weighted
    breakthrough_potential: float = 0.0  # novelty + upside weighted

    # Peer predictions about this variant
    predicted_peer_preference_fraction: float = 0.0
    predicted_survival_fraction: float = 0.0
    predicted_underrated_fraction: float = 0.0


class TripletScorecard(BaseModel):
    """Scorecard for a complete triplet: three variants scored and
    compared for role assignment.

    Operational definitions:
    - Core = highest balanced score across quality dimensions.
    - Solid = highest robustness/defensibility above minimum novelty.
    - Risky = highest breakthrough-potential above minimum coherence.
    """

    model_config = ConfigDict(extra="forbid")

    parent_kernel: str
    variant_scores: list[TripletVariantScore] = Field(default_factory=list)

    # Role assignments based on operational definitions
    assigned_core_id: str = ""
    assigned_solid_id: str = ""
    assigned_risky_id: str = ""

    # Was the original labeling confirmed or reassigned?
    roles_reassigned: bool = False
    reassignment_rationale: str = ""

    # Audit
    n_reviews: int = 0
    reviewer_ids: list[str] = Field(default_factory=list)


class ReviewerCalibrationRecord(BaseModel):
    """Calibration record for one reviewer across one run.

    Tracks how well a reviewer's predictions match outcomes.
    Used for within-run calibration updates and across-run learning.
    """

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str
    run_id: str = ""

    # How well did their quality predictions match actual peer scores?
    quality_prediction_error: float = 0.0  # MAE of predicted vs actual avg
    quality_predictions_made: int = 0

    # How well did their survival predictions match actual outcomes?
    survival_prediction_accuracy: float = 0.0  # fraction correct
    survival_predictions_made: int = 0

    # Bias patterns
    novelty_bias: float = 0.0  # positive = consistently overestimates novelty
    overrates_elegance: bool = False
    underrates_risk_takers: bool = False

    # Overall calibration score (higher = more reliable)
    calibration_score: float = 0.5  # 0.0 - 1.0

    # Weight to assign this reviewer in calibration-weighted scoring
    calibration_weight: float = 1.0
