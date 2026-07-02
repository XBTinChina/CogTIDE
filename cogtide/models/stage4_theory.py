"""Stage 4 canonical artifact: theory triplets elaborated locally per kernel.

For each Stage 3 kernel, a small local panel (5-7 experts) constructs
a triplet of theories — one core, one solid, one risky — and revises
that triplet over a few rounds. With 5 kernels and 3 theories per
triplet, Stage 4 yields 15 final theories.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cogtide.llm.normalization import coerce_list_field, coerce_string_field

TripletRole = Literal["core", "solid", "risky"]


class Stage4Theory(BaseModel):
    """One of the three theories in a Stage 4 triplet.

    The schema is deliberately rich: Stage 4 output should be detailed
    enough that a downstream modeler can build a concrete computational
    or formal model from it. In particular, ``ontology``, ``mechanism``,
    and ``formal_sketch`` together should define the variables, the
    causal structure, and (where tractable) the mathematical or
    algorithmic form of the theory.
    """

    model_config = ConfigDict(extra="forbid")

    id: str  # e.g. "T01"
    name: str
    role: TripletRole
    parent_kernel: str  # e.g. "K01"

    # Core narrative
    statement: str
    central_claim: str

    # Model-building substrate
    ontology: list[str] = Field(default_factory=list)
    mechanism: str = ""
    formal_sketch: str = ""
    boundary_conditions: list[str] = Field(default_factory=list)

    # Epistemic scaffolding
    main_assumptions: list[str] = Field(default_factory=list)
    distinctive_predictions: list[str] = Field(default_factory=list)
    testable_predictions: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)
    measurement_strategy: list[str] = Field(default_factory=list)
    phenomena_explained: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    notes: str = ""

    # v2: peer-calibrated scores from external panel
    peer_coherence: float = 0.0
    peer_defensibility: float = 0.0
    peer_novelty: float = 0.0
    peer_distinctiveness: float = 0.0
    peer_experimental_fertility: float = 0.0
    peer_upside_if_true: float = 0.0
    peer_balanced_score: float = 0.0
    role_confirmed_by_peers: bool = True

    parent_stage: str = "stage_03"
    parent_ids: list[str] = Field(default_factory=list)
    trace_path: list[str] = Field(default_factory=list)
    origin_run_id: str = ""

    @field_validator("name", "statement", "central_claim")
    @classmethod
    def _non_empty_critical_field(cls, v: str) -> str:
        """A theory with any blank required text field is junk and must
        be rejected at the boundary. Mirrors the invariant on
        ``Stage1Idea``, ``Stage2DeepTheory``, and ``Stage3Kernel``."""
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v.strip()

    @classmethod
    def from_normalized(
        cls,
        data: dict,
        *,
        theory_id: str,
        role: TripletRole,
        parent_kernel: str,
    ) -> "Stage4Theory":
        return cls(
            id=theory_id,
            name=coerce_string_field(data.get("name", "")),
            role=role,
            parent_kernel=parent_kernel,
            statement=coerce_string_field(data.get("statement", "")),
            central_claim=coerce_string_field(
                data.get("central_claim", data.get("central_explanatory_claim", ""))
            ),
            ontology=coerce_list_field(
                data.get("ontology", data.get("variables", data.get("entities", [])))
            ),
            mechanism=coerce_string_field(
                data.get("mechanism", data.get("mechanism_sketch", ""))
            ),
            formal_sketch=coerce_string_field(
                data.get("formal_sketch", data.get("formalization", data.get("model_sketch", "")))
            ),
            boundary_conditions=coerce_list_field(
                data.get("boundary_conditions", data.get("scope_conditions", []))
            ),
            main_assumptions=coerce_list_field(data.get("main_assumptions", [])),
            distinctive_predictions=coerce_list_field(
                data.get("distinctive_predictions", data.get("predictions", []))
            ),
            testable_predictions=coerce_list_field(
                data.get("testable_predictions", data.get("quantitative_predictions", []))
            ),
            falsifiers=coerce_list_field(
                data.get("falsifiers", data.get("falsifying_observations", []))
            ),
            measurement_strategy=coerce_list_field(
                data.get("measurement_strategy", data.get("operationalization", []))
            ),
            phenomena_explained=coerce_list_field(
                data.get("phenomena_explained", data.get("explains", []))
            ),
            open_questions=coerce_list_field(
                data.get("open_questions", data.get("tensions_and_open_questions", []))
            ),
            notes=coerce_string_field(data.get("notes", "")),
        )


class Stage4Triplet(BaseModel):
    """A finalized triplet for one parent kernel: core + solid + risky."""

    model_config = ConfigDict(extra="forbid")

    parent_kernel: str
    panel_expert_ids: list[str] = Field(default_factory=list)
    core_theory: Stage4Theory
    solid_theory: Stage4Theory
    risky_theory: Stage4Theory
    revision_rounds_used: int = 0
    panel_notes: str = ""

    # v2: peer-calibrated role assignment
    roles_reassigned: bool = False
    reassignment_rationale: str = ""
    peer_review_panel_ids: list[str] = Field(default_factory=list)


class Stage4TheorySet(BaseModel):
    """Canonical Stage 4 artifact: 5 triplets (15 theories total)."""

    model_config = ConfigDict(extra="forbid")

    theories: list[Stage4Theory]
    triplets: list[Stage4Triplet] = Field(default_factory=list)
