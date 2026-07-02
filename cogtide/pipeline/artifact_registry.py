"""Run-level artifact registry. Append-only artifacts.json."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from cogtide.models.manifests import ArtifactRecord
from cogtide.utils.io import read_json, write_json


class ArtifactRegistry:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "artifacts.json"
        if not self.path.exists():
            write_json(self.path, [])

    def _load(self) -> list[dict[str, Any]]:
        data = read_json(self.path)
        return data if isinstance(data, list) else []

    def add(
        self,
        artifact_id: str,
        path: Path,
        stage: str,
        substage: str,
        schema_type: str,
        *,
        parent_artifact_ids: list[str] | None = None,
        producing_agent: str = "",
        validation_status: str = "passed",
        extra: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        rec = ArtifactRecord(
            artifact_id=artifact_id,
            path=str(path.relative_to(self.run_dir)) if path.is_absolute() else str(path),
            stage=stage,
            substage=substage,
            schema_type=schema_type,
            parent_artifact_ids=parent_artifact_ids or [],
            producing_agent=producing_agent,
            validation_status=validation_status,  # type: ignore[arg-type]
            timestamp=datetime.utcnow().isoformat() + "Z",
            extra=extra or {},
        )
        records = self._load()
        records.append(rec.model_dump())
        write_json(self.path, records)
        return rec

    def all(self) -> list[ArtifactRecord]:
        return [ArtifactRecord.model_validate(r) for r in self._load()]
