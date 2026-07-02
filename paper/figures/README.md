# CogTIDE paper figures

Editable Mermaid source for the manuscript figures. These `.mmd` files are the
**canonical, version-controlled source** for the paper figures — edit them here,
then export to PDF/SVG/PNG for the manuscript (do not hand-edit exported images).

All three reflect the actual pipeline as implemented in `cogtide/`; when the code
changes, update these diagrams to match.

## Figures

### `fig1_pipeline.mmd` — End-to-end pipeline (Stage 0 -> 4)
The full flow from an open-ended research question to 15 theory candidates:
question -> `QuestionDossier` -> 57 raw ideas (19 experts x 3 risk levels +
challenger pass) -> blind peer review / scorecards -> deep theories (D..) ->
kernel hypotheses (K..) -> core/solid/risky triplets -> 15 theories (5 triplets).
Peer-review and external-panel checkpoints between stages show that promotion is
governed by outsider review and forecast skill, not synthesis fluency. Names the
canonical artifacts each stage writes, plus run provenance (`run_meta.json`,
`artifacts.json`).

### `fig2_scoring_calibration.mmd` — Scoring & calibration
How a single blind peer review (direct dimension ratings, peer predictions,
survival forecast) is aggregated into the four scorecard signals — `quality_score`,
`unexpected_support` (actual - predicted), `survival_forecast`, and
`calibration_weighted_score` — and how reviewer calibration
(`calibration_score = 0.5*quality_calibration + 0.5*survival_accuracy`;
`calibration_weight = 0.5 + 0.5*calibration_score`, clamped to `[0.5, 1.0]`) is
folded into the calibration-weighted score used by the stage judge to rank and
promote. A feedback edge shows realized outcomes re-estimating reviewer calibration.

### `fig3_memory_artifact_loop.mmd` — Cross-run memory / artifact loop
The cross-run loop: a run's artifacts, per-run calibration records, and compiled
`RunMemoryRecord` are persisted under `memory/` (`raw/`, `project_memory.json` +
`topics/`, `calibration/` with `aggregate.json`, and the allow-listed
`learned/active/policy.yaml` overlay). On the next run these are re-loaded and the
policy overlay is merged into the run config at startup via `apply_policy_overlay()`,
the calibration aggregate is loaded as reviewer weights, and memory context is
retrieved (advisory, opt-in per stage). Also shows artifact lineage:
ideas (I..) -> deep theories (D..) -> kernels (K..) -> theories (T..).

## Rendering

The files use standard Mermaid `flowchart` syntax and are self-contained (no theme
or plugin required).

- **Browser (quickest):** open <https://mermaid.live>, paste the file contents,
  and export SVG/PNG.
- **CLI (`mermaid-cli` / `mmdc`)**, for reproducible exports:

  ```bash
  npm install -g @mermaid-js/mermaid-cli
  mmdc -i fig1_pipeline.mmd            -o fig1_pipeline.pdf
  mmdc -i fig2_scoring_calibration.mmd -o fig2_scoring_calibration.svg
  mmdc -i fig3_memory_artifact_loop.mmd -o fig3_memory_artifact_loop.png
  ```

- **Editors:** VS Code (Mermaid preview extensions), Obsidian, and GitHub all
  render fenced ` ```mermaid ` blocks; paste the file body into such a block to
  preview inline.

## Responsible-use note

The figures describe an audit-first *generation* pipeline. Its outputs are
**hypotheses for expert review**, not validated scientific conclusions.
