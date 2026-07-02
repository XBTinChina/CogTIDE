"""Stage 1 canonical artifact: raw ideas from the fixed expert society."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cogtide.llm.normalization import coerce_list_field, coerce_string_field

RiskLevel = Literal["grounded", "medium", "bold"]
PreservationMark = Literal["UNIQUE", "RISKY", "SPECIAL"]


class Stage1Idea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # e.g. "I001"
    title: str
    core_claim: str
    mechanism: str
    explains: list[str] = Field(default_factory=list)
    main_assumptions: list[str] = Field(default_factory=list)
    distinctive_prediction: str
    why_interesting: str
    source_lens: str  # the expert id, e.g. "expert_01_reinforcement_learning"
    risk_level: RiskLevel
    preservation_marks: list[PreservationMark] = Field(default_factory=list)

    # Traceability metadata
    parent_stage: str = "stage_00"
    parent_ids: list[str] = Field(default_factory=list)
    trace_path: list[str] = Field(default_factory=list)
    origin_run_id: str = ""

    @field_validator("title", "core_claim", "mechanism", "distinctive_prediction", "why_interesting")
    @classmethod
    def _non_empty_critical_field(cls, v: str) -> str:
        """An idea with any blank required text field is junk and must be
        rejected at the boundary. Without this, a permissive coercer turns
        LLM responses with mostly-empty fields into structurally valid
        Stage1Idea objects that then leak into Stage 2 idea packets.

        The five fields covered (title, core_claim, mechanism,
        distinctive_prediction, why_interesting) are the ones the markdown
        renderer prints unconditionally; if any one is blank the rendered
        idea looks 'empty'.
        """
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v.strip()

    @classmethod
    def from_normalized(cls, data: dict, *, idea_id: str, source_lens: str) -> "Stage1Idea":
        risk = data.get("risk_level") or data.get("risk") or "medium"
        if risk not in ("grounded", "medium", "bold"):
            # Coerce common variants from the LLM.
            r = str(risk).lower()
            if "ground" in r or "safe" in r or "conservative" in r:
                risk = "grounded"
            elif "bold" in r or "wild" in r or "speculative" in r:
                risk = "bold"
            else:
                risk = "medium"

        return cls(
            id=idea_id,
            title=coerce_string_field(data.get("title", "")),
            core_claim=coerce_string_field(data.get("core_claim", "")),
            mechanism=coerce_string_field(data.get("mechanism", "")),
            explains=coerce_list_field(data.get("explains", data.get("what_it_explains", []))),
            main_assumptions=coerce_list_field(data.get("main_assumptions", data.get("assumptions", []))),
            distinctive_prediction=coerce_string_field(
                data.get("distinctive_prediction", data.get("prediction", ""))
            ),
            why_interesting=coerce_string_field(
                data.get("why_interesting", data.get("why_it_is_interesting", ""))
            ),
            source_lens=source_lens,
            risk_level=risk,  # type: ignore[arg-type]
        )


class Stage1IdeaSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ideas: list[Stage1Idea]
    expert_ids: list[str] = Field(default_factory=list)
    challenger_round_count: int = 0
