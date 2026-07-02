# Contributing to cogTIDE

Thanks for your interest in improving **cogTIDE** (Cognitive Theory Ideation,
Debate, and Epistemic Evaluation). This document explains how to set up a
development environment and the conventions we follow.

## Ways to contribute

- Report bugs and unexpected behavior via GitHub issues.
- Improve documentation (README, `HOW_IT_WORKS.md`, prompt clarity).
- Add or refine pipeline stages, agents, prompts, schemas, or evaluation logic.
- Add tests for pure, network-free logic.
- Add support/examples for additional OpenAI-compatible providers.

## Development setup

```bash
git clone https://github.com/XBTinChina/CogTIDE.git
cd CogTIDE
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set an API key if you want to run the live
pipeline. Most unit tests do **not** require a key or network access.

## Running tests

```bash
pytest -q
```

Please keep new unit tests **network-free and deterministic** — mock or avoid
LLM calls. Tests that need a live provider should be clearly marked and skipped
by default.

## Coding conventions

- Target Python 3.10+.
- Match the surrounding style: type hints, `from __future__ import annotations`,
  small focused functions, and docstrings that explain *why*, not *what*.
- Keep the pipeline **auditable**: any new artifact should be written to the run
  directory with a stable schema and traceable IDs/lineage.
- Do not hardcode secrets. Configuration goes in `configs/`; keys come from the
  environment or `.env`.
- Keep the project provider-agnostic — depend only on the OpenAI-compatible
  chat-completions surface, not a specific vendor.

## Prompts and schemas

- Agent prompts live under `prompts/` and are registered in `configs/agents.yaml`.
- Canonical artifact schemas live under `schemas/`; regenerate with
  `python scripts/export_schemas.py` when you change a Pydantic model in
  `cogtide/models/`.

## Responsible use

cogTIDE produces **hypotheses**, not validated scientific findings. When
contributing features or examples, avoid framing generated theories as
established results, and preserve the disclaimers in user-facing output.

## Pull requests

1. Create a feature branch.
2. Keep changes focused; update docs and tests alongside code.
3. Ensure `pytest -q` passes and the CLI still starts
   (`python -m cogtide.cli --help`).
4. Describe the change and its motivation in the PR description.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
