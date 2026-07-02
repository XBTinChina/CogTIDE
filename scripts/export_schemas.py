"""Export Pydantic v2 models as JSON Schemas into schemas/.

Run: python scripts/export_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

from cogtide.models import (
    ArtifactRecord,
    QuestionDossier,
    Stage1Idea,
    Stage1IdeaSet,
    Stage2DeepTheory,
    Stage2DeepTheorySet,
    Stage3Kernel,
    Stage3KernelSet,
    Stage4Theory,
    Stage4TheorySet,
    Stage4Triplet,
    SubstageManifest,
)

OUT = Path(__file__).resolve().parents[1] / "schemas"

MODELS = {
    "question_dossier": QuestionDossier,
    "stage1_idea": Stage1Idea,
    "stage1_idea_set": Stage1IdeaSet,
    "stage2_deep_theory": Stage2DeepTheory,
    "stage2_deep_theory_set": Stage2DeepTheorySet,
    "stage3_kernel": Stage3Kernel,
    "stage3_kernel_set": Stage3KernelSet,
    "stage4_theory": Stage4Theory,
    "stage4_theory_set": Stage4TheorySet,
    "stage4_triplet": Stage4Triplet,
    "substage_manifest": SubstageManifest,
    "artifact_record": ArtifactRecord,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
