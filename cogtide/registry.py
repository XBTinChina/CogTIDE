"""Agent registry. Loads configs/agents.yaml into a typed lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cogtide.utils.io import read_text

AGENTS_PATH = Path(__file__).resolve().parent.parent / "configs" / "agents.yaml"


@dataclass
class AgentSpec:
    id: str
    stage: str
    substage: str
    prompt: str
    role: str
    output_schema: str | None = None
    model: str | None = None
    temperature: float | None = None
    preservation_oriented: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    def __init__(self, agents: list[AgentSpec]):
        self._by_id: dict[str, AgentSpec] = {a.id: a for a in agents}
        self._by_stage: dict[str, list[AgentSpec]] = {}
        for a in agents:
            self._by_stage.setdefault(a.stage, []).append(a)

    @classmethod
    def load(cls, path: Path | str = AGENTS_PATH) -> "AgentRegistry":
        data = yaml.safe_load(read_text(path)) or []
        agents: list[AgentSpec] = []
        known = {f.name for f in AgentSpec.__dataclass_fields__.values()}
        for entry in data:
            # Unknown top-level keys are collected into extra. An explicit
            # `extra:` mapping in the YAML (e.g. expert_index/domain on the
            # Stage 1 experts) must be merged in too — `extra` is itself a
            # dataclass field name, so the comprehension alone drops it.
            extra = {k: v for k, v in entry.items() if k not in known}
            explicit_extra = entry.get("extra")
            if isinstance(explicit_extra, dict):
                extra = {**explicit_extra, **extra}
            spec = AgentSpec(
                id=entry["id"],
                stage=entry["stage"],
                substage=entry["substage"],
                prompt=entry["prompt"],
                role=entry.get("role", ""),
                output_schema=entry.get("output_schema"),
                model=entry.get("model"),
                temperature=entry.get("temperature"),
                preservation_oriented=bool(entry.get("preservation_oriented", False)),
                extra=extra,
            )
            agents.append(spec)
        return cls(agents)

    def get(self, agent_id: str) -> AgentSpec:
        return self._by_id[agent_id]

    def for_stage(self, stage: str) -> list[AgentSpec]:
        return list(self._by_stage.get(stage, []))

    def for_substage(self, stage: str, substage: str) -> list[AgentSpec]:
        return [a for a in self.for_stage(stage) if a.substage == substage]

    def all(self) -> list[AgentSpec]:
        return list(self._by_id.values())
