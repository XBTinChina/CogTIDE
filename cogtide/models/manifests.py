"""Substage manifest and artifact registry record models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ValidationStatus = Literal["pending", "passed", "failed", "skipped"]


class SubstageManifest(BaseModel):
    """One manifest per substage execution. Written by CheckpointManager."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    stage: str  # "stage_00".."stage_04"
    substage: str  # "S00.01".."S04.07"
    started_at: str
    finished_at: str = ""
    input_artifact_ids: list[str] = Field(default_factory=list)
    prompt_paths: list[str] = Field(default_factory=list)
    model: str = ""
    temperature: float = 0.0
    raw_output_paths: list[str] = Field(default_factory=list)
    normalized_output_paths: list[str] = Field(default_factory=list)
    validation_status: ValidationStatus = "pending"
    validation_path: str = ""
    output_artifact_ids: list[str] = Field(default_factory=list)
    notes: str = ""

    @classmethod
    def new(cls, run_id: str, stage: str, substage: str) -> "SubstageManifest":
        return cls(
            run_id=run_id,
            stage=stage,
            substage=substage,
            started_at=datetime.utcnow().isoformat() + "Z",
        )


class ArtifactRecord(BaseModel):
    """One row in artifacts.json (the run-level artifact registry)."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    path: str
    stage: str
    substage: str
    schema_type: str  # "QuestionDossier" / "Stage1IdeaSet" / etc.
    parent_artifact_ids: list[str] = Field(default_factory=list)
    producing_agent: str = ""
    validation_status: ValidationStatus = "pending"
    timestamp: str
    extra: dict[str, Any] = Field(default_factory=dict)
