"""Checkpoint manager: substage-manifest schema and API for audit/resume.

Substage manifests live at runs/<run_id>/manifests/<stage>_<substage>.json.
A manifest records inputs, prompts, raw output paths, normalized output
paths, validation status, and output artifact IDs; ``is_complete`` /
``latest_complete_substage`` skip substages whose
validation_status == "passed".

Current status: this manager is instantiated on every ``RunContext`` and
defines the manifest schema, but the shipped stage drivers do not yet call
``write(...)`` — they persist canonical stage artifacts directly and resume
by re-loading those files (see the controller's ``load_*_from_run``
helpers). Wiring manifest writes into every substage is a planned
extension; see HOW_IT_WORKS.md §1.5.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cogtide.models.manifests import SubstageManifest
from cogtide.utils.io import read_json, write_json


class CheckpointManager:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.manifest_dir = self.run_dir / "manifests"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, stage: str, substage: str) -> Path:
        safe_substage = substage.replace(".", "_")
        return self.manifest_dir / f"{stage}_{safe_substage}.json"

    def write(self, manifest: SubstageManifest) -> Path:
        manifest.finished_at = datetime.utcnow().isoformat() + "Z"
        path = self._manifest_path(manifest.stage, manifest.substage)
        write_json(path, manifest.model_dump())
        return path

    def read(self, stage: str, substage: str) -> SubstageManifest | None:
        path = self._manifest_path(stage, substage)
        if not path.exists():
            return None
        return SubstageManifest.model_validate(read_json(path))

    def is_complete(self, stage: str, substage: str) -> bool:
        m = self.read(stage, substage)
        return m is not None and m.validation_status == "passed"

    def latest_complete_substage(self, stage: str) -> str | None:
        completed = []
        for path in sorted(self.manifest_dir.glob(f"{stage}_*.json")):
            data = read_json(path)
            if data.get("validation_status") == "passed":
                completed.append(data["substage"])
        return completed[-1] if completed else None
