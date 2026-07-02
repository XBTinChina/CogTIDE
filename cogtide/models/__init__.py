"""Pydantic v2 schemas for canonical stage artifacts.

Every model uses extra='forbid' so unexpected fields fail loudly. Coercion
of polymorphic LLM output happens in cogtide/llm/normalization.py *before*
construction reaches these models.
"""

from .question_dossier import QuestionDossier
from .stage1_idea import Stage1Idea, Stage1IdeaSet
from .stage2_deep_theory import (
    CoalitionAttempt,
    CoalitionMember,
    Stage2DeepTheory,
    Stage2DeepTheorySet,
)
from .stage3_kernel import CouncilAttempt, Stage3Kernel, Stage3KernelSet
from .stage4_theory import Stage4Theory, Stage4TheorySet, Stage4Triplet
from .manifests import SubstageManifest, ArtifactRecord
from .review_signals import (
    DimensionRating,
    PeerRating,
    PeerPrediction,
    PeerReviewEnvelope,
    IdeaPeerReviewSet,
    TheoryPeerReviewSet,
    TripletPeerReview,
)
from .scorecards import (
    DimensionAggregate,
    IdeaScorecard,
    DeepTheoryScorecard,
    KernelScorecard,
    TripletVariantScore,
    TripletScorecard,
    ReviewerCalibrationRecord,
)

__all__ = [
    "QuestionDossier",
    "Stage1Idea",
    "Stage1IdeaSet",
    "CoalitionMember",
    "CoalitionAttempt",
    "Stage2DeepTheory",
    "Stage2DeepTheorySet",
    "CouncilAttempt",
    "Stage3Kernel",
    "Stage3KernelSet",
    "Stage4Theory",
    "Stage4TheorySet",
    "Stage4Triplet",
    "SubstageManifest",
    "ArtifactRecord",
    # v2 peer-prediction types
    "DimensionRating",
    "PeerRating",
    "PeerPrediction",
    "PeerReviewEnvelope",
    "IdeaPeerReviewSet",
    "TheoryPeerReviewSet",
    "TripletPeerReview",
    "DimensionAggregate",
    "IdeaScorecard",
    "DeepTheoryScorecard",
    "KernelScorecard",
    "TripletVariantScore",
    "TripletScorecard",
    "ReviewerCalibrationRecord",
]
