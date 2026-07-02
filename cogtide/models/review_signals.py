"""Peer-prediction review signal models.

These models capture the blind peer elicitation layer that v2 adds
between raw idea generation (Stage 1) and coalition synthesis (Stage 2),
and between synthesis outputs and acceptance decisions in Stages 2-4.

Each review contains:
- direct ratings on quality dimensions,
- predictions of how other reviewers will rate the item,
- predictions of whether the item will survive downstream stages,
- short failure-mode notes.

This is not a theorem-pure peer-prediction mechanism. It is a
peer-prediction-inspired elicitation layer for open-ended theory work.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewTargetKind = Literal["idea", "deep_theory", "kernel", "triplet_variant"]


class DimensionRating(BaseModel):
    """A single rating on one quality dimension (1-10 scale)."""

    model_config = ConfigDict(extra="forbid")

    dimension: str  # e.g. "novelty", "coherence", "testability"
    score: float  # 1.0 - 10.0
    confidence: float = 0.5  # 0.0 - 1.0, reviewer self-assessed confidence
    note: str = ""


class PeerRating(BaseModel):
    """Direct ratings from one reviewer on one item."""

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str  # expert_id of the reviewing agent
    target_id: str  # id of the item being reviewed (e.g. "I007", "D03")
    target_kind: ReviewTargetKind
    ratings: list[DimensionRating] = Field(default_factory=list)
    overall_quality: float = 0.0  # 1.0 - 10.0, summary rating
    failure_modes: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    brief_assessment: str = ""


class PeerPrediction(BaseModel):
    """Predictions about how other reviewers will rate the same item.

    This is the core peer-prediction signal: reviewers predict what
    others will think, not just what they think themselves.
    """

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str
    target_id: str
    target_kind: ReviewTargetKind

    # "What score do you predict the average reviewer will give?"
    predicted_avg_quality: float = 0.0  # 1.0 - 10.0
    predicted_dimension_avgs: list[DimensionRating] = Field(default_factory=list)

    # "Will this item contribute to an accepted downstream artifact?"
    predicted_survival_probability: float = 0.5  # 0.0 - 1.0
    predicted_survival_rationale: str = ""

    # "Is this overrated or underrated relative to what peers will think?"
    overrated_underrated: Literal["overrated", "fair", "underrated"] = "fair"
    overrated_underrated_rationale: str = ""


class PeerReviewEnvelope(BaseModel):
    """Complete blind review from one reviewer for one item:
    direct ratings + predictions bundled together."""

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str
    target_id: str
    target_kind: ReviewTargetKind
    rating: PeerRating
    prediction: PeerPrediction
    review_round: int = 1  # which review round this came from


class IdeaPeerReviewSet(BaseModel):
    """All peer reviews collected for Stage 1 ideas before Stage 2."""

    model_config = ConfigDict(extra="forbid")

    reviews: list[PeerReviewEnvelope] = Field(default_factory=list)
    reviewer_ids: list[str] = Field(default_factory=list)
    reviewed_idea_ids: list[str] = Field(default_factory=list)
    reviews_per_idea: int = 0


class TheoryPeerReviewSet(BaseModel):
    """Peer reviews collected for deep theories or kernels by an
    external panel that did not participate in the synthesis."""

    model_config = ConfigDict(extra="forbid")

    reviews: list[PeerReviewEnvelope] = Field(default_factory=list)
    reviewer_ids: list[str] = Field(default_factory=list)
    reviewed_item_ids: list[str] = Field(default_factory=list)
    panel_kind: str = ""  # "stage2_external", "stage3_external", "stage4_external"


class TripletPeerReview(BaseModel):
    """Peer review of a complete triplet (core + solid + risky).

    Reviewers rate each variant separately AND predict which variant
    peers will prefer / which will survive later scrutiny.
    """

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str
    parent_kernel: str
    core_rating: PeerRating
    solid_rating: PeerRating
    risky_rating: PeerRating
    predicted_preferred_variant: Literal["core", "solid", "risky"] = "core"
    predicted_surviving_variant: Literal["core", "solid", "risky"] = "solid"
    predicted_underrated_variant: Literal["core", "solid", "risky"] = "risky"
    rationale: str = ""
