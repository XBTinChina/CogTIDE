"""Stage 0 canonical artifact: clarified question dossier."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cogtide.llm.normalization import coerce_list_field, coerce_string_field


class QuestionDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_question: str
    clarified_question: str
    core_question: str
    target_phenomenon: str
    why_it_matters: str
    scope: str
    constraints: list[str] = Field(default_factory=list)
    background_context: str = ""
    relevant_distinctions: list[str] = Field(default_factory=list)
    known_assumptions: list[str] = Field(default_factory=list)
    context_file_note: str = ""
    remaining_open_points: list[str] = Field(default_factory=list)
    consolidated_summary: str

    @classmethod
    def from_normalized(cls, data: dict) -> "QuestionDossier":
        """Construct from a normalized LLM dict, coercing polymorphic fields."""
        return cls(
            original_question=coerce_string_field(data.get("original_question", "")),
            clarified_question=coerce_string_field(data.get("clarified_question", "")),
            core_question=coerce_string_field(data.get("core_question", "")),
            target_phenomenon=coerce_string_field(data.get("target_phenomenon", "")),
            why_it_matters=coerce_string_field(data.get("why_it_matters", "")),
            scope=coerce_string_field(data.get("scope", "")),
            constraints=coerce_list_field(data.get("constraints", [])),
            background_context=coerce_string_field(data.get("background_context", "")),
            relevant_distinctions=coerce_list_field(data.get("relevant_distinctions", [])),
            known_assumptions=coerce_list_field(data.get("known_assumptions", [])),
            context_file_note=coerce_string_field(data.get("context_file_note", "")),
            remaining_open_points=coerce_list_field(data.get("remaining_open_points", [])),
            consolidated_summary=coerce_string_field(data.get("consolidated_summary", "")),
        )
