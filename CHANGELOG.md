# Changelog

All notable changes to cogTIDE are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Unreleased

First open-source release of **cogTIDE** (Cognitive Theory Ideation, Debate,
and Epistemic Evaluation), migrated and rebranded from an internal
theory-generation prototype.

### Added
- Staged theory-generation pipeline (Stage 0–4): question clarification,
  multi-agent ideation, peer-screened coalition synthesis, council/kernel
  synthesis, and core/solid/risky theory triplets.
- Peer-prediction scoring, reviewer calibration, survival forecasting, and
  calibration-weighted scorecards.
- Cross-run memory (raw/topic/project records) and a learned policy overlay.
- Auditable run artifacts with traceable IDs and lineage.
- Provider-agnostic LLM client for any OpenAI-compatible chat endpoint.
- Documentation: `README.md`, `README.zh-CN.md`, `HOW_IT_WORKS.md`, with a
  documentation navigation panel linking them alongside Contributing and License.
- Open-source hygiene: MIT `LICENSE`, `CITATION.cff`, `CONTRIBUTING.md`,
  `.env.example`, `.gitignore`, and a network-free unit test suite.

### Changed
- Rebranded from the internal name/`TtD` prototype to **cogTIDE**; Python
  package and CLI renamed to `cogtide`.
- LLM client made provider-agnostic (`LLMClient`); configuration defaults to a
  generic OpenAI-compatible endpoint with keys supplied via the environment.

### Fixed
- Calibration: Stage 2 external-panel survival forecasts are now scored
  against the observable Stage 3 outcome (did the deep theory contribute
  to an accepted kernel?) once Stage 3 completes, via a survival-only
  update that leaves the already-recorded quality components untouched.
  Previously these next-stage forecasts were never checked against
  next-stage reality.
- Packaging: a non-editable `pip install .` now ships all subpackages
  (previously only the top-level package was included and the CLI crashed
  with `ModuleNotFoundError`).
- Agent registry: explicit `extra:` mappings in `configs/agents.yaml`
  (expert domains and ordering) are no longer dropped, so idea
  `source_lens` values carry real domain names again.
- Blind-review reviewer assignment is now deterministic across interpreter
  runs (seeded with a stable hash instead of Python's randomized `hash()`).
- Malformed numeric fields in LLM review output (null / nested objects /
  strings) no longer crash a whole review batch; they coerce to defaults.
- The adaptive "underrated" threshold now flags items at the minimum
  sample size and matches its documented top-quartile behavior.
- Idea scorecards record the authoring expert in `source_lens` (previously
  the idea's own ID was stored).
- A malformed learned-policy overlay can no longer wipe the entire stage
  configuration; non-dict `stages:` values are rejected.
- Resuming a run no longer overwrites the original `run_meta.json` audit
  record; Stage 0 re-runs resume from the latest dossier instead of an
  arbitrary one.
- `external_panel_size` (Stages 2–4) and Stage 4's `expert_max` config
  knobs are now actually read; unused knobs were removed from
  `configs/pipeline.yaml`; Stage 3 council fill stops at `expert_min` as
  documented.
- `scripts/export_schemas.py` now also exports the peer-review-envelope,
  idea-scorecard, and triplet-scorecard schemas, replacing three stale
  hand-written files.
- Placeholder values shipped in `.env.example` are skipped by the `.env`
  loader; the Windows `.env.txt` rename hint checks the right filename.
- Documentation corrections: memory ships enabled-by-default (not
  "opt-in"), per-target review-dimension sets, `.markdown` ingestion,
  and non-configurable structural constants are now stated accurately.

### Removed
- NotebookLM / NLM / MCP integration and all related code, prompts, config,
  dependencies, and tests, in favor of a generic, transparent pipeline.
- Private/generated artifacts (previous runs, cross-run memory, personal
  research materials) and any embedded credentials.
- Seven orphaned v1 prompt duplicates that no code or config referenced.
