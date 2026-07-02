# cogTIDE

**Cognitive Theory Ideation, Debate, and Epistemic Evaluation** — a
peer-calibrated, audit-first LLM pipeline for theory generation in psychology,
cognitive neuroscience, and cognitive science.

cogTIDE turns an open-ended research question into a set of candidate scientific
theories through a multi-stage pipeline. What distinguishes it from naively
"asking an LLM for theories" is that every promotion between stages is governed
by outsider peer review, forecast skill, and downstream survival — not by
synthesis fluency — and every artifact it produces is traceable back to the
ideas it came from.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

> ## ⚠️ Responsible use — read this first
>
> **cogTIDE produces hypotheses, not validated scientific conclusions.**
> The theories it generates are candidate ideas intended to support expert
> ideation and review. They are *not* peer-reviewed findings, and they have not
> been checked against experiment or against the empirical literature.
>
> - LLM outputs can be **wrong, fabricated, out of date, or biased**. Treat
>   every claim, mechanism, and predicted effect as unverified.
> - The internal peer-prediction and calibration scores measure *relative*
>   review signal among model-generated reviewers — they are **not** a measure
>   of scientific truth or of real-world validity.
> - Nothing here substitutes for domain expertise, a proper literature review,
>   preregistration, or empirical testing.
>
> Use cogTIDE as a brainstorming and auditing aid, and subject every output to
> human expert judgment before acting on it.

---

## What cogTIDE does

cogTIDE runs a five-stage, audit-first pipeline (Stage 0 → Stage 4) that
transforms a research question into structured theory candidates:

- **Multi-agent ideation** — a registry of domain-expert agents generates raw
  ideas across several risk levels, plus a challenger pass.
- **Peer-screened synthesis** — blind peer review and scorecards decide which
  ideas advance; coalitions draft, critique, and elaborate them into deeper
  theories, with an external reviewer panel.
- **Peer prediction** — each reviewer reports not only their own ratings but
  what they expect *other* reviewers to say, plus a probability that the item
  survives the next stage. Items that draw more support than predicted
  ("unexpected support") are surfaced.
- **Reviewer calibration** — reviewers are scored on how well their forecasts
  match reality across runs; sharper reviewers earn more weight in the
  calibration-weighted score.
- **Cross-run memory** — an opt-in, advisory memory subsystem lets later runs
  learn from earlier ones (topic snapshots, reviewer calibration, and an
  allow-listed learned-policy overlay).
- **Full traceability** — every canonical artifact carries stable IDs and
  lineage fields, and each run records its own provenance, so any final theory
  can be traced back through kernels, deep theories, and the original ideas.

## How the pipeline works

The pipeline is a sequence of stages; each stage reads the canonical artifacts
of the previous one and writes its own under `runs/<run_id>/`. Stage knobs
(agent counts, panel sizes, targets, memory toggles) live in
`configs/pipeline.yaml`.

- **Stage 0 — Question clarification.** An interactive clarifier loop
  normalizes the raw question into a `QuestionDossier`. It can ingest local
  materials from a matching subfolder under `question/` and, optionally, prior-
  run memory. A confirmation gate must pass before the run proceeds (skippable
  with `--non-interactive`). Writes `stage_00/question-*.json` / `.md`.
- **Stage 1 — Multi-agent ideation.** 19 domain-expert agents each generate
  ideas across 3 risk levels (19 × 3 = 57 raw ideas), followed by a challenger
  pass. Writes `stage_01/raw-ideas-*.json`.
- **Stage 2 — Peer-screened coalition synthesis.** Blind peer review and
  scorecards rank the ideas; coalitions then draft and critique them into deep
  theories, scored by an external reviewer panel. Writes
  `idea-peer-reviews.json`, `idea-scorecards.json`,
  `external-panel-reviews-D*.json`, and `coalition-deep-theories-*.json`.
- **Stage 3 — Council / kernel synthesis.** A facilitated council works across
  the deep theories to produce kernel hypotheses, scored by an external panel.
  Writes `council-kernels-*.json` / `.md` and `external-panel-reviews-K*.json`.
- **Stage 4 — Theory triplets.** Each kernel is expanded into a
  **core / solid / risky** triplet, peer-scored and revised, with a
  plain-language explainer. Writes `triplet-theories-*.json` / `.md`,
  `triplet-scorecard-K*.json`, and `triplet-peer-reviews-K*.json`.

A typical run yields **15 final theories organized as 5 triplets**
(core / solid / risky per kernel), though these counts are configurable.

## Repository layout

```
CogTIDE/
├── cogtide/               # Python package (import as `cogtide`)
│   ├── cli.py             # command-line entry point
│   ├── registry.py        # agent registry loader
│   ├── stages/            # stage_00 … stage_04 drivers
│   ├── pipeline/          # controller, run context, checkpoints, artifacts
│   ├── evaluation/        # scoring, peer review, calibration, forecasting
│   ├── memory/            # cross-run memory: store, retrieval, policy, compiler
│   ├── models/            # pydantic models for dossiers, ideas, theories, scorecards
│   ├── llm/               # OpenAI-compatible client, retry, prompt building
│   ├── reporting/         # stage markdown renderers
│   ├── validators/        # artifact preservation checks
│   └── utils/             # ids, io, text helpers
├── configs/               # models.yaml, retries.yaml, pipeline.yaml, agents.yaml
├── prompts/               # per-stage + shared/memory prompt templates
├── schemas/               # JSON Schemas for every canonical artifact
├── scripts/               # utilities (e.g. export_schemas.py)
├── tests/                 # unit tests
├── question/              # drop local materials here for Stage 0 (scaffold only)
├── paper/                 # manuscript / preprint sources (TODO)
├── pyproject.toml
├── .env.example           # copy to .env and add your API key
├── CITATION.cff
├── LICENSE                # MIT
└── README.md
```

`runs/` (per-run artifacts) and `memory/` (cross-run memory) are **generated at
runtime and git-ignored** — they may contain unpublished research material and
must never be committed. Anything you add under `question/` is git-ignored too;
only the scaffold is tracked.

## Prerequisites

- **Python 3.10+**.
- Access to an **OpenAI-compatible chat-completions endpoint** and an **API
  key** for it. cogTIDE talks to any provider that speaks the OpenAI
  chat-completions protocol — OpenAI, Zhipu GLM, Moonshot Kimi, or a local
  server such as vLLM or Ollama.

## Installation

Prompts, configs, and schemas are loaded relative to the repository root, so an
editable install from a clone is the supported path.

```bash
git clone https://github.com/XBTinChina/CogTIDE.git   # TODO: confirm final URL
cd CogTIDE

python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate

pip install -e .                          # runtime
pip install -e ".[dev]"                   # + test dependencies (pytest)
```

## Configuration

All configuration lives under `configs/`. **API keys never go in these files** —
they are read from the environment or a repo-root `.env`.

### `configs/models.yaml` — provider (OpenAI-compatible, provider-agnostic)

Set `api_base_url`, `model`, and the name of the environment variable that holds
your key (`api_key_env`, with `fallback_api_key_env` tried if the first is
unset). Point it at whichever provider you have access to:

```yaml
default:
  provider: openai-compatible
  api_base_url: https://api.openai.com/v1   # OpenAI
  # api_base_url: https://open.bigmodel.cn/api/paas/v4   # Zhipu GLM
  # api_base_url: http://localhost:11434/v1              # local Ollama
  api_key_env: LLM_API_KEY
  fallback_api_key_env: OPENAI_API_KEY
  model: gpt-4o
  temperature: 1.0
  max_tokens: 8192
  response_format_json: true
```

### `configs/retries.yaml` — reliability & rate limiting

Retry attempts and waits, request timeout, `concurrency_limit`, a minimum
interval between calls, and a rate-limit backoff multiplier. The defaults are
deliberately conservative (serial execution, ~30 requests/min) so they are safe
on low-tier accounts; raise them only after confirming your provider allows more
throughput.

### `configs/pipeline.yaml` — stage knobs & memory toggles

Per-stage counts (experts, ideas per expert, coalition size, panel sizes,
targets) and the memory subsystem's settings, including the per-stage
`memory.per_stage` toggles. Memory is opt-in.

### `configs/agents.yaml`

The agent registry (id, stage, substage, prompt, role, schema) that the pipeline
loads at startup.

### API keys via `.env`

```bash
cp .env.example .env
# then edit .env and set your key, e.g.:
#   LLM_API_KEY=sk-...
```

`.env` is git-ignored. Shell-exported variables take precedence over `.env`
values. Never commit real keys.

## Quick start

Run the whole pipeline on a question:

```bash
python -m cogtide.cli run --topic "How does prior expectation shape perception?"
```

The editable install also provides a console script, so this is equivalent:

```bash
cogtide run --topic "How does prior expectation shape perception?"
```

Stage 0 is interactive by default (it asks you to confirm the clarified
question). Add `--non-interactive` to skip that gate for automated runs.

## Running the pipeline

### Full pipeline (Stage 0 → Stage 4)

```bash
cogtide run --topic "..."                    # interactive Stage 0 gate
cogtide run --topic "..." --non-interactive  # skip the gate
```

Each run prints its `run_id`; all artifacts land under `runs/<run_id>/`.

### Stage by stage

Stage 0 creates the run; every later stage resumes it by `run_id` and assumes
the prior stages' canonical artifacts already exist.

```bash
cogtide stage_00 --topic "..."      # → prints a run_id
cogtide stage_01 --resume <run_id>
cogtide stage_02 --resume <run_id>
cogtide stage_03 --resume <run_id>
cogtide stage_04 --resume <run_id>
```

### Resume

To finish a run that already has Stage 0 + Stage 1 artifacts (runs Stages 2–4):

```bash
cogtide resume_pipeline --resume <run_id>
```

(All commands work identically as `python -m cogtide.cli <command> ...`.)

## Running with local materials

To give Stage 0 project-specific context, drop `.md`, `.txt`, or `.rst` files
into a topic subfolder under `question/`:

```
question/
└── expectation-perception/
    ├── notes.md
    ├── prior-work.txt
    └── open-questions.rst
```

When you run Stage 0, cogTIDE scans `question/` for the subfolder whose name
best matches your question (simple token overlap). If it finds a candidate it
asks you to confirm; if several match, you pick one. All supported files in the
confirmed subfolder are concatenated (up to a character budget) and handed to
the clarifier as background context. Materials you add under `question/` are
git-ignored, so unpublished notes stay local.

## Outputs and artifacts

Every run writes to `runs/<run_id>/`, with one subdirectory per stage plus
run-level provenance:

```
runs/<run_id>/
├── run_meta.json          # run_id, topic, model, resolved config
├── artifacts.json         # registry of canonical artifacts (lineage/provenance)
├── stage_00/
│   └── question-<slug>-<ts>.json / .md      # QuestionDossier
├── stage_01/
│   └── raw-ideas-<run_id>.json              # ideas I001…
├── stage_02/
│   ├── idea-peer-reviews.json
│   ├── idea-scorecards.json
│   ├── external-panel-reviews-D*.json
│   └── coalition-deep-theories-<run_id>.json  # deep theories D…
├── stage_03/
│   ├── council-kernels-<run_id>.json / .md    # kernels K…
│   └── external-panel-reviews-K*.json
└── stage_04/
    ├── triplet-peer-reviews-K*.json
    ├── triplet-scorecard-K*.json
    └── triplet-theories-<run_id>.json / .md   # final theories (5 triplets)
```

Canonical artifacts carry stable IDs (ideas `I001…`, deep theories `D…`, kernels
`K…`, final theories) and lineage fields (`contributing_idea_ids`,
`contributing_deep_theory_ids`, and so on), so any final theory can be traced
back through the stages it came from.

## How scoring, calibration, and memory work

Each review collects direct dimension ratings (coherence, defensibility,
novelty, distinctiveness, fertility, upside), **peer predictions** (what a
reviewer expects other reviewers to say), **survival forecasts** (the
probability an item passes the next stage), and over/under-rated flags. From
these, scorecards derive signals including `quality_score`, `unexpected_support`
(actual minus predicted), `survival_forecast`, and `calibration_weighted_score`.

Reviewers are then **calibrated** across runs:

```
calibration_score = 0.5 * quality_calibration + 0.5 * survival_accuracy
weight            = 0.5 + 0.5 * calibration_score      # clamped to [0.5, 1.0]
```

Sharper (better-calibrated) reviewers receive more weight in the
calibration-weighted score. The **memory** subsystem (`memory/`) stores a raw
record per run, topic snapshots, project memory, and per-run/aggregate
calibration; an allow-listed learned-policy overlay
(`memory/learned/active/`) can be merged into the config at startup. Memory is
advisory and opt-in per stage.

For a deeper walkthrough of the scoring, calibration, and memory machinery, see
[HOW_IT_WORKS.md](HOW_IT_WORKS.md).

## Limitations

- **LLM hallucination.** Generated theories, mechanisms, and predictions may be
  fabricated, wrong, or internally inconsistent, and may misrepresent the
  literature.
- **Unvalidated hypotheses.** Outputs are candidate ideas for expert review, not
  validated findings; they have not been tested empirically.
- **Peer prediction is not ground truth.** The scoring and calibration signals
  reflect agreement and forecast skill *among model-generated reviewers*, not
  scientific correctness.
- **Provider dependence.** Results depend heavily on the model and provider you
  configure; different endpoints and versions can yield materially different
  theories.
- **Non-determinism.** Runs are stochastic (temperature, sampling, retries);
  repeating a run will not reproduce identical outputs.
- **Cost and latency.** A full run makes many LLM calls across all stages and
  can be slow and expensive depending on your provider and rate limits.

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for how
to set up a development environment, run the tests (`pip install -e ".[dev]"`
then `pytest`), and open issues or pull requests.

## Citation

If you use cogTIDE in your research, please cite it. Machine-readable metadata is
in [CITATION.cff](CITATION.cff). A plain BibTeX entry (fill in the TODO fields
once finalized):

```bibtex
@software{cogtide,
  title   = {cogTIDE: A Peer-Calibrated LLM Pipeline for Auditable Theory
             Generation in Psychology, Cognitive Neuroscience, and Cognitive
             Science},
  author  = {TODO: confirm full author list},
  year    = {TODO: confirm year},
  version = {0.1.0},
  license = {MIT},
  url     = {https://github.com/XBTinChina/CogTIDE},
  note    = {TODO: add DOI once a preprint/archive (e.g. bioRxiv, Zenodo) is minted}
}
```

## License

Released under the **MIT License**. See [LICENSE](LICENSE) for the full text.

## Acknowledgments

cogTIDE builds on the broader open-source LLM and scientific-Python ecosystems.
TODO: add funding sources, institutional affiliations, and any other
acknowledgments before public release.
