"""Stage 3 canonical artifact: kernel theories from council synthesis.

Stage 3 takes the 15 Stage 2 deep theories and forms small councils of
3 deep theories + 5-7 key experts. Each council discusses for a
configurable number of rounds and either yields one accepted "kernel"
or fails. The stage repeats until `target_count` kernels are accepted
(default 5).

Unlike the original ttm-theory-atlas Stage 3 design (six kernels with
exactly five paragraphs each), this Stage 3 produces five kernels and
treats each kernel as a single coherent statement plus rationale and
preservation notes — the deeper substrate that explains why three
already-deep theories share an architecture.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cogtide.llm.normalization import coerce_list_field, coerce_string_field

from .stage1_idea import PreservationMark


class Stage3Kernel(BaseModel):
    """One accepted kernel produced by a Stage 3 council."""

    model_config = ConfigDict(extra="forbid")

    id: str  # e.g. "K01"
    name: str
    kernel_statement: str
    deeper_substrate: str  # the shared architecture/principle the council found
    rationale: str  # why this is deeper than the 3 input deep theories
    mechanism_sketch: str = ""
    key_predictions: list[str] = Field(default_factory=list)
    key_assumptions: list[str] = Field(default_factory=list)
    preserved_tensions: str = ""

    contributing_deep_theory_ids: list[str] = Field(default_factory=list)
    council_expert_ids: list[str] = Field(default_factory=list)
    contributing_idea_ids: list[str] = Field(default_factory=list)
    contributing_expert_ids: list[str] = Field(default_factory=list)
    preserved_marks: list[PreservationMark] = Field(default_factory=list)

    discussion_summary: str = ""
    judge_notes: str = ""

    # v2: peer-prediction scorecard attached at acceptance
    peer_quality_score: float = 0.0
    peer_unexpected_support: float = 0.0
    peer_survival_forecast: float = 0.0
    peer_calibration_weighted_score: float = 0.0
    peer_reviewer_disagreement: float = 0.0
    peer_is_underrated: bool = False
    peer_is_locally_persuasive_only: bool = False
    peer_panel_notes: str = ""

    parent_stage: str = "stage_02"
    parent_ids: list[str] = Field(default_factory=list)
    trace_path: list[str] = Field(default_factory=list)
    origin_run_id: str = ""

    @field_validator("name", "kernel_statement", "deeper_substrate", "rationale")
    @classmethod
    def _non_empty_critical_field(cls, v: str) -> str:
        """A kernel with any blank required text field is junk and must
        be rejected at the boundary. Mirrors the invariant on
        ``Stage1Idea`` and ``Stage2DeepTheory``."""
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v.strip()

    @classmethod
    def from_normalized(
        cls,
        data: dict,
        *,
        kernel_id: str,
        contributing_deep_theory_ids: list[str],
        council_expert_ids: list[str],
        contributing_idea_ids: list[str],
        contributing_expert_ids: list[str],
        preserved_marks: list[str],
        judge_notes: str,
    ) -> "Stage3Kernel":
        return cls(
            id=kernel_id,
            name=coerce_string_field(data.get("name", "")),
            kernel_statement=coerce_string_field(
                data.get("kernel_statement", data.get("statement", ""))
            ),
            deeper_substrate=coerce_string_field(data.get("deeper_substrate", "")),
            rationale=coerce_string_field(data.get("rationale", "")),
            mechanism_sketch=coerce_string_field(data.get("mechanism_sketch", "")),
            key_predictions=coerce_list_field(data.get("key_predictions", [])),
            key_assumptions=coerce_list_field(data.get("key_assumptions", [])),
            preserved_tensions=coerce_string_field(data.get("preserved_tensions", "")),
            contributing_deep_theory_ids=contributing_deep_theory_ids,
            council_expert_ids=council_expert_ids,
            contributing_idea_ids=contributing_idea_ids,
            contributing_expert_ids=contributing_expert_ids,
            preserved_marks=[m for m in preserved_marks if m in ("UNIQUE", "RISKY", "SPECIAL")],  # type: ignore[misc]
            discussion_summary=coerce_string_field(data.get("discussion_summary", "")),
            judge_notes=judge_notes,
        )


class CouncilAttempt(BaseModel):
    """Audit record for one Stage 3 council attempt, accepted or not."""

    model_config = ConfigDict(extra="forbid")

    attempt_index: int
    council_deep_theory_ids: list[str] = Field(default_factory=list)
    council_expert_ids: list[str] = Field(default_factory=list)
    candidate_name: str = ""
    candidate_statement: str = ""
    discussion_summary: str = ""
    accepted: bool = False
    accepted_kernel_id: str = ""
    rejection_reason: str = ""


class Stage3KernelSet(BaseModel):
    """Canonical Stage 3 artifact: the accepted kernels plus the full
    attempt log so analysts can audit failed councils."""

    model_config = ConfigDict(extra="forbid")

    kernels: list[Stage3Kernel]
    attempts: list[CouncilAttempt] = Field(default_factory=list)
    target_count: int = 5
