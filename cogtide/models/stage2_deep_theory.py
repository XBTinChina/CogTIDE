"""Stage 2 canonical artifact: deep theories from coalition synthesis.

Stage 2 takes Stage 1 raw ideas and forms small expert coalitions of
5 experts (each bringing one idea). Each coalition discusses for a
configurable number of rounds and either yields one accepted "deep
theory" or fails. The stage repeats until `target_count` deep theories
are accepted (default 15).

This file defines the canonical artifact, the per-attempt record, and
the coalition member shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cogtide.llm.normalization import coerce_list_field, coerce_string_field

from .stage1_idea import PreservationMark


class CoalitionMember(BaseModel):
    """One participant in a Stage 2 coalition: an expert + the idea they
    brought into the coalition."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str  # e.g. "expert_01_reinforcement_learning"
    idea_id: str    # e.g. "I007"


class Stage2DeepTheory(BaseModel):
    """One accepted deep theory produced by a Stage 2 coalition."""

    model_config = ConfigDict(extra="forbid")

    id: str  # e.g. "D01"
    name: str
    statement: str
    rationale: str  # why this is deeper than the input ideas
    mechanism_sketch: str = ""
    key_predictions: list[str] = Field(default_factory=list)
    key_assumptions: list[str] = Field(default_factory=list)
    tensions_and_open_questions: str = ""

    coalition_members: list[CoalitionMember] = Field(default_factory=list)
    contributing_idea_ids: list[str] = Field(default_factory=list)
    contributing_expert_ids: list[str] = Field(default_factory=list)
    preserved_marks: list[PreservationMark] = Field(default_factory=list)

    discussion_summary: str = ""  # condensed view of the multi-round discussion
    judge_notes: str = ""

    # v2: peer-prediction scorecard attached at acceptance
    peer_quality_score: float = 0.0
    peer_unexpected_support: float = 0.0
    peer_survival_forecast: float = 0.0
    peer_calibration_weighted_score: float = 0.0
    peer_reviewer_disagreement: float = 0.0
    peer_is_underrated: bool = False
    peer_panel_notes: str = ""

    parent_stage: str = "stage_01"
    parent_ids: list[str] = Field(default_factory=list)
    trace_path: list[str] = Field(default_factory=list)
    origin_run_id: str = ""

    @field_validator("name", "statement", "rationale")
    @classmethod
    def _non_empty_critical_field(cls, v: str) -> str:
        """A deep theory with any blank required text field is junk and
        must be rejected at the boundary. Without this, a permissive
        coercer turns LLM responses with mostly-empty fields into
        structurally valid objects that then leak into downstream stages
        and render as empty `## [D01]` entries in the markdown artifact.

        Mirrors the invariant on ``Stage1Idea`` in ``stage1_idea.py``."""
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v.strip()

    @classmethod
    def from_normalized(
        cls,
        data: dict,
        *,
        deep_theory_id: str,
        coalition_members: list[CoalitionMember],
        judge_notes: str,
        preserved_marks: list[str],
    ) -> "Stage2DeepTheory":
        return cls(
            id=deep_theory_id,
            name=coerce_string_field(data.get("name", "")),
            statement=coerce_string_field(data.get("deep_theory_statement", data.get("statement", ""))),
            rationale=coerce_string_field(data.get("rationale", "")),
            mechanism_sketch=coerce_string_field(data.get("mechanism_sketch", "")),
            key_predictions=coerce_list_field(data.get("key_predictions", [])),
            key_assumptions=coerce_list_field(data.get("key_assumptions", [])),
            tensions_and_open_questions=coerce_string_field(
                data.get("tensions_and_open_questions", "")
            ),
            coalition_members=coalition_members,
            contributing_idea_ids=[m.idea_id for m in coalition_members],
            contributing_expert_ids=sorted({m.expert_id for m in coalition_members}),
            preserved_marks=[m for m in preserved_marks if m in ("UNIQUE", "RISKY", "SPECIAL")],  # type: ignore[misc]
            discussion_summary=coerce_string_field(data.get("discussion_summary", "")),
            judge_notes=judge_notes,
        )


class CoalitionAttempt(BaseModel):
    """Audit record for one Stage 2 coalition attempt, accepted or not."""

    model_config = ConfigDict(extra="forbid")

    attempt_index: int
    coalition_members: list[CoalitionMember] = Field(default_factory=list)
    candidate_name: str = ""
    candidate_statement: str = ""
    discussion_summary: str = ""
    accepted: bool = False
    accepted_deep_theory_id: str = ""
    rejection_reason: str = ""


class Stage2DeepTheorySet(BaseModel):
    """Canonical Stage 2 artifact: the accepted deep theories plus the
    full attempt log so analysts can audit failed coalitions."""

    model_config = ConfigDict(extra="forbid")

    deep_theories: list[Stage2DeepTheory]
    attempts: list[CoalitionAttempt] = Field(default_factory=list)
    target_count: int = 15
