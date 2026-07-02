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
- Documentation: `README.md`, `README.zh-CN.md`, `HOW_IT_WORKS.md`.
- Preprint manuscript draft and editable Mermaid figures under `paper/`.
- Open-source hygiene: MIT `LICENSE`, `CITATION.cff`, `CONTRIBUTING.md`,
  `.env.example`, `.gitignore`, and a network-free unit test suite.

### Changed
- Rebranded from the internal name/`TtD` prototype to **cogTIDE**; Python
  package and CLI renamed to `cogtide`.
- LLM client made provider-agnostic (`LLMClient`); configuration defaults to a
  generic OpenAI-compatible endpoint with keys supplied via the environment.

### Removed
- NotebookLM / NLM / MCP integration and all related code, prompts, config,
  dependencies, and tests, in favor of a generic, transparent pipeline.
- Private/generated artifacts (previous runs, cross-run memory, personal
  research materials) and any embedded credentials.
