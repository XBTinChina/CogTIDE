# CogTIDE: A Peer-Calibrated LLM Pipeline for Auditable Theory Generation in Psychology, Cognitive Neuroscience, and Cognitive Science

<!--
  Software manuscript (bioRxiv / PLOS Computational Biology style).
  cogTIDE = Cognitive Theory Ideation, Debate, and Epistemic Evaluation.
  Prose/toolbox name: cogTIDE. Python package + CLI: cogtide. Repo/paper: CogTIDE.
-->

**Authors:** TODO: Author One^1^, TODO: Author Two^2^, TODO: Author N^1,2^

**Affiliations:**
1. TODO: Department, Institution, City, Country.
2. TODO: Department, Institution, City, Country.

**ORCIDs:** TODO: 0000-0000-0000-0000 (Author One); TODO: additional ORCIDs.

**Corresponding author:** TODO: Name, email (`TODO: corresponding@institution.edu`).

**Date:** TODO: preprint date.

**Version:** 0.1.0

---

## Abstract

Large language models (LLMs) can produce fluent, superficially plausible
scientific theories on demand, but "ask-an-LLM-for-theories" workflows offer no
principled way to decide which candidate ideas are worth an expert's attention,
and they leave no trail explaining why one idea was promoted over another. We
present **cogTIDE** (Cognitive Theory Ideation, Debate, and Epistemic
Evaluation), an open-source, audit-first Python pipeline that transforms an
open-ended research question in psychology, cognitive neuroscience, or cognitive
science into a structured set of candidate theories. cogTIDE runs five stages:
question clarification, multi-agent expert ideation (19 domain-expert agents
across three risk levels, plus a challenger pass), peer-screened coalition
synthesis, council/kernel synthesis, and expansion of each kernel into a
core/solid/risky theory triplet. The distinguishing design choice is that
promotions between stages are governed not by synthesis fluency but by *outsider
peer review, forecast skill, and downstream survival*. Every reviewer reports
direct dimension ratings, peer predictions (what they expect other reviewers to
say), and a survival forecast; scorecards derive a quality score, an unexpected-
support signal, a survival forecast, and a calibration-weighted score. Reviewers
are calibrated across runs, and better-calibrated reviewers earn more weight. An
opt-in, advisory cross-run memory subsystem with an allow-listed learned-policy
overlay lets later runs benefit from earlier ones. Every canonical artifact
carries stable IDs and lineage fields, so any final theory can be traced back to
the ideas it came from. cogTIDE is provider-agnostic (any OpenAI-compatible
endpoint) and MIT-licensed. Generated theories are hypotheses for expert review,
not validated conclusions.

*(~250 words. TODO: trim/expand to the target journal's exact word limit.)*

## Author Summary

Modern chatbots will happily invent scientific theories, and the results often
*read* like the real thing. That is precisely the problem: a confident,
well-written paragraph is not evidence that an idea is novel, coherent, or worth
testing, and a single model has no way to show its work. Researchers who want to
use these tools for genuine ideation are left sorting fluent text by hand, with
no record of why any idea rose to the top.

cogTIDE is a free, open-source tool that treats theory generation like a small,
transparent scientific community rather than a single oracle. It takes a research
question and runs it through several stages. First, many simulated domain experts
propose ideas at different levels of ambition. Then other simulated experts —
who did not write those ideas — review them blindly, and crucially each reviewer
also predicts what their peers will think and whether an idea will survive to the
next round. Ideas that draw more support than the crowd expected are surfaced,
reviewers who forecast well are given more weight over time, and the strongest
ideas are elaborated into families of theories that span a safe-to-bold spectrum.

Everything cogTIDE does is written down. Each idea, theory, and score has a
stable identifier, and each final theory can be traced back through the stages it
came from. The goal is not to replace scientists but to give them a systematic,
auditable brainstorming partner whose outputs are clearly labelled as hypotheses
to be checked, not conclusions to be trusted.

## Introduction

The release of instruction-tuned LLMs has made it trivial to request scientific
theories in natural language, and the outputs are frequently articulate,
on-topic, and confident. This fluency is seductive and misleading. Fluency is a
property of the text, not of the idea: a model can produce a paragraph that reads
like a mechanistic theory while the underlying claim is vague, unfalsifiable,
already well known, internally inconsistent, or simply fabricated. TODO: add
citation for the LLM-ideation / research-idea-generation literature (e.g., recent
studies comparing LLM-generated research ideas to human ideas). TODO: add
citation for work on LLM hallucination and confident fabrication.

Naive prompting has three deeper deficits beyond hallucination. **First, there is
no selection principle.** If a model returns twenty theories, nothing in the
workflow ranks them by anything other than the model's own (or the user's)
impression, and single-model self-evaluation tends to reward the same surface
features — elegance, generality, familiar vocabulary — that make weak ideas look
strong. **Second, there is no calibration.** A one-shot judgment carries no
information about whether the judge is any good; there is no notion of a reviewer
who reliably forecasts what a community will value. **Third, there is no audit
trail.** A theory that emerges from a long chat has no traceable provenance: one
cannot ask which earlier idea it descends from, which reviewers supported it, or
why it was promoted rather than a competitor. For scientific use these are not
cosmetic gaps; they are the difference between a brainstorming toy and an
instrument whose behavior can be inspected, contested, and reproduced.

The gap, then, is a system that (a) *generates* broadly and at controlled levels
of risk, (b) *selects* using signals more robust than single-model fluency, (c)
*calibrates* its own evaluators against observed outcomes, and (d) *records*
enough provenance that every promotion can be audited after the fact.

cogTIDE addresses this gap. Its contribution is not a new base model but an
*evaluation-first orchestration* around any capable chat model. Concretely,
cogTIDE contributes: (1) a five-stage generation-and-selection architecture in
which each stage consumes the audited artifacts of the previous one; (2) a
peer-prediction scoring layer in which reviewers report both their own ratings
and their expectations of peers, yielding an "unexpected support" signal that
highlights ideas more compelling than the crowd predicted; (3) a reviewer-
calibration loop that rewards forecast skill across runs; (4) an opt-in,
advisory cross-run memory subsystem with an allow-listed learned-policy overlay;
and (5) a fully traceable artifact model with stable IDs and lineage fields.
Throughout, cogTIDE is explicit that its outputs are hypotheses for expert
review, and that its internal scores measure *relative review signal among
model-generated reviewers*, not scientific truth.

## Design and Implementation

### Overview

cogTIDE is a Python package (`cogtide`, import as `from cogtide ...`) with a
command-line interface (`python -m cogtide.cli` or the `cogtide` console script).
It orchestrates a sequence of stages; each stage reads the canonical artifacts of
the previous stage and writes its own under `runs/<run_id>/`. Stage knobs (agent
counts, panel sizes, targets, memory toggles) live in `configs/pipeline.yaml`, so
the architecture is configurable without code changes. A single `RunContext`
(`cogtide/pipeline/run_context.py`) is created at start-up and threaded through
every stage; it owns the run directory, the LLM client, the checkpoint manager,
the artifact registry, and the agent registry, and it holds the merged
configuration (models + retries + pipeline, with any learned-policy overlay
applied).

Figure 1 shows the end-to-end pipeline.

**Figure 1. The five-stage cogTIDE pipeline.** Source:
`paper/figures/fig1_pipeline.mmd`. Stage 0 clarifies the question into a
`QuestionDossier`; Stage 1 generates raw ideas from 19 domain-expert agents
across three risk levels plus a challenger pass; Stage 2 applies blind peer
review and scorecards, then coalition drafting/critique into deep theories scored
by an external panel; Stage 3 runs a facilitated council over deep theories to
produce kernel hypotheses, scored by an external panel; Stage 4 expands each
kernel into a core/solid/risky triplet, peer-scored and revised, with a
plain-language explainer. Arrows carry canonical artifacts with stable IDs; each
promotion is gated by peer signal rather than synthesis fluency.

### The five stages

The stage drivers live in `cogtide/stages/stage_00.py` … `stage_04.py`, invoked
through `cogtide/pipeline/controller.py`.

- **Stage 0 — Question clarification** (`stage_00.py`). An interactive clarifier
  loop (up to `max_clarification_rounds`, default 5) normalizes the raw question
  into a `QuestionDossier`. It can ingest local materials from the best-matching
  subfolder under `question/` (concatenating `.md`/`.txt`/`.rst` files up to a
  character budget) and, optionally, prior-run memory. A confirmation gate must
  pass before the run proceeds; `--non-interactive` skips the gate for automated
  runs. Writes `stage_00/question-*.json` / `.md`.

- **Stage 1 — Multi-agent ideation** (`stage_01.py`). Nineteen domain-expert
  agents (`expert_count: 19`) each generate ideas across three risk levels
  (`ideas_per_expert: 3`), yielding 19 × 3 = 57 raw ideas, followed by a
  challenger pass (default 2 rounds over chunks of 10 ideas) that stress-tests
  them. Writes `stage_01/raw-ideas-*.json` with ideas identified `I001…`.

- **Stage 2 — Peer-screened coalition synthesis** (`stage_02.py`). Blind peer
  review and scorecards rank the ideas (default 3 reviewers per idea); coalitions
  (default size 5) then draft and critique the surviving ideas into deep
  theories, which are scored by an external reviewer panel (default size 5). A
  pool multiplier over-generates candidates before a top-K trim ranks them by
  composite peer score. Writes `idea-peer-reviews.json`, `idea-scorecards.json`,
  `external-panel-reviews-D*.json`, and `coalition-deep-theories-*.json` with
  deep theories identified `D…`.

- **Stage 3 — Council / kernel synthesis** (`stage_03.py`). A facilitated
  council works across small sets of deep theories (`council_theory_size: 3`,
  `expert_min`/`expert_max` = 5–7) to distil kernel hypotheses (default target
  5), scored by an external panel. Writes `council-kernels-*.json` / `.md` and
  `external-panel-reviews-K*.json` with kernels identified `K…`.

- **Stage 4 — Core/solid/risky theory triplets** (`stage_04.py`). Each kernel is
  expanded into a **core / solid / risky** triplet, peer-scored and revised
  (default 2 revision rounds), with an optional plain-language explainer pass.
  Writes `triplet-theories-*.json` / `.md`, `triplet-scorecard-K*.json`, and
  `triplet-peer-reviews-K*.json`. A per-attempt token budget schedule
  (`triplet_max_tokens_schedule`, default `[12000, 24000, 48000]`) lets a
  truncated first attempt recover on retry.

A typical run yields **15 final theories organized as 5 triplets** (core / solid
/ risky per kernel); all counts are configurable in `configs/pipeline.yaml`.

### Agents

Agents are declared in `configs/agents.yaml` and loaded by the `AgentRegistry`
(`cogtide/registry.py`). Each entry specifies an `id`, `stage`, `substage`,
`prompt` file, `role`, and optional schema/extra fields. Roles include the 19
Stage 1 `expert` agents (spanning domains such as reinforcement learning,
Bayesian inference, control theory, dynamical systems, information theory,
cognitive science, neuroscience, decision making, sensory systems, social
cognition, development/learning, motor control, linguistic communication, music
and rhythm, ecological/embodied cognition, complex systems, computational
neuroscience, machine learning, and mathematics), plus a `challenger`, and the
`drafter`, `critic`, `judge`, `facilitator`, `constructor`, `reviser`,
`explainer`, and the `peer_reviewer` / `external_reviewer` / `triplet_reviewer`
roles that drive peer-prediction scoring. Prompts live under `prompts/`, split
into per-stage directories and a `shared/` set of base contracts (traceability,
preservation, JSON/output contracts, reasoning, and framework aids). The shared
framework-aids prompt (`prompts/shared/BASE_framework_aids.md`) offers classical
lenses — Marr's levels of analysis, Tinbergen's four questions, the
descriptive/mechanistic/normative distinction, control-theoretic and dynamical-
systems vocabularies, and philosophy-of-science reminders (falsifiability,
parsimony, explanatory vs predictive power) — explicitly *as thinking aids, not
mandatory bins*.

### Artifacts, IDs, and lineage

Every canonical artifact is a validated JSON document with a JSON Schema under
`schemas/`. Artifacts carry stable IDs (ideas `I001…`, deep theories `D…`,
kernels `K…`, final theories) and lineage fields (`contributing_idea_ids`,
`contributing_deep_theory_ids`, and so on). Two run-level files record
provenance: `run_meta.json` (run_id, topic, model, resolved config) and
`artifacts.json`, an append-only registry maintained by the `ArtifactRegistry`
(`cogtide/pipeline/artifact_registry.py`). Each `ArtifactRecord` row stores the
artifact ID, path, stage/substage, `schema_type`, `parent_artifact_ids`,
producing agent, validation status, and timestamp (schema:
`schemas/artifact_record.schema.json`). Because lineage is explicit at every hop,
any final theory can be traced back through kernels, deep theories, and the
original ideas that seeded it.

### Configuration

All configuration lives under `configs/` and API keys never appear in these
files. `configs/models.yaml` describes an OpenAI-compatible provider
(`api_base_url`, `model`, `temperature`, `max_tokens`, `response_format_json`,
and `api_key_env`/`fallback_api_key_env` naming the environment variables that
hold the key). `configs/retries.yaml` sets retry attempts and waits, request
timeout, `concurrency_limit`, a minimum inter-request interval, a rate-limit
backoff multiplier, and jitter; the shipped defaults are deliberately
conservative (serial execution, ~30 requests/min) to be safe on low-tier
accounts. `configs/pipeline.yaml` holds per-stage knobs and the memory
subsystem's toggles. `configs/agents.yaml` is the agent registry.

### Provider-agnostic LLM client

The LLM client (`cogtide/llm/client.py`) is a single async wrapper over any
endpoint that speaks the OpenAI chat-completions protocol — OpenAI, Zhipu GLM,
Moonshot Kimi, Together, Groq, a local vLLM or Ollama server, and similar. It is
built on the `openai` Python SDK's `AsyncOpenAI` and adds three layers of
rate-limit hardening: bounded concurrency via an `asyncio.Semaphore`; a global
token-bucket rate limiter enforcing a minimum wall-clock gap between calls across
all stages; and 429-aware retry backoff that detects rate-limit errors, honors
`Retry-After` headers, applies the configured multiplier, and adds jitter so
concurrent failing calls do not retry in lockstep. A `chat_json` helper requests
JSON mode and normalizes the response. Every call produces a `CallRecord`
(agent, model, temperature, max_tokens, prompts, raw response, attempts,
finish reason, normalization report), which supports auditing and truncation
recovery.

### Reproducibility and audit trail

cogTIDE is designed to be inspected. Each run is self-contained under
`runs/<run_id>/` with `run_meta.json` capturing the resolved configuration and
model, and `artifacts.json` recording the provenance of every canonical
artifact. Reviewer selection is seeded (see Methods) so that, holding inputs
fixed, the *assignment* of reviewers to items is deterministic even though the
LLM outputs themselves are not. Prompts, configs, and schemas are versioned in
the repository and loaded relative to the repository root, which is why an
editable install from a clone is the supported path. Because the run directory
may contain unpublished research material, `runs/` and the cross-run `memory/`
tree are git-ignored by default and must never be committed.

## Epistemic Evaluation Framework

cogTIDE's central claim is that promotions are governed by peer signal, not
synthesis fluency. The machinery implementing this lives in
`cogtide/evaluation/` (peer review, scoring, forecasting, calibration) and
`cogtide/memory/`. Figure 2 summarizes the scoring and calibration flow.

**Figure 2. Peer prediction, scorecards, and reviewer calibration.** Source:
`paper/figures/fig2_scoring_calibration.mmd`. Each blind review contributes
direct dimension ratings and peer predictions; scorecards aggregate these into
quality, unexpected-support, survival-forecast, and calibration-weighted
signals; observed outcomes feed reviewer calibration, which reweights future
scores.

### Blind peer review and peer prediction

Peer review is orchestrated by `cogtide/evaluation/peer_review.py`. The governing
principle is that reviewers never see other reviewers' ratings before submitting
their own, which is what makes predictions about peer opinion informative. Each
review collects, per item:

- **Direct dimension ratings** on a 1–10 scale. The dimension set depends on the
  target kind: ideas are rated on novelty, mechanistic promise, coherence,
  distinctiveness, and testability; deep theories and kernels on depth,
  mechanistic clarity, coherence, distinctiveness, testability, and
  non-averaging; and triplet variants on coherence, defensibility, novelty,
  distinctiveness, experimental fertility, and upside-if-true. Each review also
  reports an overall quality score, strengths, and failure modes.
- **Peer predictions** — what the reviewer expects the *average* reviewer to give
  on each dimension and overall.
- **Survival forecasts** — the probability that the item passes the next stage,
  with a rationale.
- **Over/under-rated flags** — whether the item is likely overrated, underrated,
  or fairly rated relative to peer opinion, and (for theories/kernels) whether it
  is "only locally persuasive" (convincing within its own framing but not to an
  outsider).

### Scorecards

`cogtide/evaluation/scoring.py` turns raw reviews into scorecards. The key
signals are:

- **quality_score** — the mean overall-quality rating across reviewers.
- **unexpected_support** — actual peer support minus predicted peer support,
  averaged across reviewers. This is the peer-prediction signal proper: a
  positive value marks an item that reviewers found *more* compelling than they
  expected their peers to find it — the zone where under-appreciated but strong
  candidates live.
- **survival_forecast** — the mean predicted survival probability.
- **calibration_weighted_score** — the quality score reweighted by reviewer
  calibration (see below); with no calibration weights it reduces to the plain
  quality score.

Scorecards also record reviewer disagreement (the standard deviation of overall
quality), per-dimension aggregates (mean rating, mean prediction, and their
difference), and an `is_underrated` flag. For a *batch* of ideas the underrated
threshold is adaptive by default: it is a percentile (default 0.75) of the run's
own distribution of unexpected-support values, floored at zero, which keeps the
flag meaningful even though LLM reviewers as a group tend to under-predict the
crowd. Single-item paths (individual deep theories and kernels) use a fixed
threshold because no distribution is available. For triplets, operational
definitions assign the core/solid/risky roles from peer scores — core = highest
balanced score, solid = highest robustness above a minimum novelty, risky =
highest breakthrough potential above a minimum coherence — and record whether the
peer-scored roles differ from the originally labelled ones.

### Reviewer calibration and survival forecasting

`cogtide/evaluation/forecasting.py` compares reviewers' predictions against
observed outcomes. For each reviewer it computes the mean absolute error between
their predicted average quality and the actual average quality per item; the
accuracy of their survival predictions (a prediction counts as correct when a
forecast ≥ 0.5 matches survival, or < 0.5 matches non-survival); and their bias
on individual dimensions (e.g., novelty). From these it builds a
`ReviewerCalibrationRecord` per reviewer with a calibration score and a weight
(exact formulas in Methods). `cogtide/evaluation/calibration.py` merges these
records within and across runs via count-weighted running averages and exposes
`compute_calibration_weights` for the scoring layer. It also identifies
cross-item patterns for memory: *false positives* (accepted, high-quality items
that nonetheless failed downstream) and *underrated winners* (items with modest
initial quality but high unexpected support that survived anyway).

### Memory and the policy overlay

The opt-in, advisory cross-run memory subsystem lives in `cogtide/memory/` and
is stored under a git-ignored `memory/` tree (Figure 3). Its layout comprises
`raw/<run_id>.json` (one `RunMemoryRecord` per completed run), `topics/`
(per-topic snapshots), `project_memory.json` (a compressed project snapshot),
`calibration/` (per-run records plus `aggregate.json`), and a `learned/` tree
with `active/`, `pending/`, and `archive/` policy directories plus a
`learning_log/`. Memory records are explicitly marked non-authoritative: they are
optional context from prior model runs, not evidence and not a constraint to
preserve past theories. Memory is opt-in per stage via `memory.per_stage` toggles
in `configs/pipeline.yaml`.

The **learned-policy overlay** (`cogtide/memory/policy.py`) is the one place
where cross-run learning can influence configuration, and it is deliberately
constrained. At start-up `RunContext.create` merges `models.yaml` and
`pipeline.yaml` and then applies the active policy overlay. The overlay loader
allow-lists exactly which keys may be overridden (only `stages`, and within a
stage only a fixed set such as target counts, coalition/council sizes, attempt
budgets, and revision rounds); anything else in a policy file is ignored. This
keeps the self-learning layer auditable and prevents memory from silently
rewriting arbitrary configuration.

**Figure 3. The memory and artifact-lineage loop.** Source:
`paper/figures/fig3_memory_artifact_loop.mmd`. Each run emits canonical
artifacts with lineage IDs and a run memory record; the memory compiler distils
topic and project snapshots and aggregate calibration; and, when enabled, an
allow-listed learned-policy overlay and retrieved memory advise later runs.

## Use Cases

cogTIDE is intended as a systematic, auditable ideation aid. Illustrative uses
include:

- **Hypothesis generation in cognitive neuroscience, psychology, and cognitive
  science.** A researcher facing an open question (for example, how prior
  expectations shape perception) can obtain a spread of candidate theories at
  controlled risk levels, each with a plain-language explainer and a scorecard,
  to seed a literature review, a lab discussion, or a grant's aims. The
  core/solid/risky triplet structure makes the safe-to-bold spectrum explicit.

- **Structured brainstorming with an audit trail.** Because every idea, theory,
  and score has a stable ID and traceable lineage, cogTIDE suits settings where
  it matters *why* a candidate was surfaced — for instance, revisiting a run
  months later, or comparing how two questions were explored.

- **Teaching theory construction and peer review.** The explicit dimensions
  (coherence, defensibility, novelty, distinctiveness, testability, fertility)
  and the peer-prediction mechanics make the pipeline a concrete teaching object:
  students can inspect scorecards, see where reviewers disagreed, and examine the
  difference between an idea's actual and predicted support.

- **Methodological research on LLM evaluation.** cogTIDE provides a reproducible
  test-bed for studying peer prediction, reviewer calibration, and survival
  forecasting among model-generated reviewers, since all reviews, scorecards, and
  calibration records are persisted.

In every case the outputs are candidate hypotheses for expert judgment. cogTIDE
does not establish that a theory is correct, novel relative to the literature, or
worth pursuing; it organizes and prioritizes candidates and documents the basis
for that prioritization.

## Demonstration / Results

This section describes the *kind* of output cogTIDE produces. Every concrete
number, figure, and table below is a placeholder to be filled from a real run;
we deliberately report no invented metrics.

A completed run on a single research question produces:

- **A clarified question.** A `QuestionDossier` (`stage_00/question-*.json/.md`)
  with the normalized question and any ingested local materials. TODO: include
  the example question used for the demonstration run.
- **Raw ideas.** Typically 57 ideas (`I001…`) across three risk levels plus
  challenger critiques (`stage_01/raw-ideas-*.json`). TODO: report the actual
  idea count and the risk-level distribution for the demonstration run.
- **Idea scorecards.** Per-idea quality, unexpected-support, survival-forecast,
  and calibration-weighted scores, with underrated flags
  (`idea-scorecards.json`). TODO: insert a table of the top-ranked ideas with
  their scores. TODO: insert a figure of the unexpected-support distribution.
- **Deep theories and kernels.** Deep theories (`D…`) with external-panel
  reviews, and kernel hypotheses (`K…`) with panel scores. TODO: report how many
  deep theories and kernels were produced and their score ranges.
- **Final theories.** A set of theory triplets — in the default configuration
  **15 theories organized as 5 core/solid/risky triplets** — each with a
  plain-language explainer and a triplet scorecard
  (`triplet-theories-*.json/.md`, `triplet-scorecard-K*.json`). TODO: present one
  full triplet verbatim as a worked example, clearly labelled as an unvalidated
  hypothesis.
- **Calibration records.** Per-reviewer calibration scores and weights
  (`memory/calibration/*.json`). TODO: report the calibration-score distribution
  and which reviewer roles were best/worst calibrated.
- **Audit artifacts.** `run_meta.json` and `artifacts.json` capturing the model,
  resolved configuration, and full lineage. TODO: show a lineage trace for one
  final theory back to its contributing ideas.

TODO: report run cost and wall-clock time (number of LLM calls per stage, tokens,
provider, and model) for the demonstration run. TODO: if multiple models or
providers were compared, summarize how outputs differed. TODO: any comparison
against a naive single-prompt baseline must come from a real, described
protocol — do not report a number here without one.

## Discussion

**What cogTIDE establishes.** cogTIDE demonstrates that LLM-based theory
generation can be made *systematic and auditable*: broad generation at controlled
risk, selection by peer signal rather than single-model fluency, evaluators that
are calibrated against observed outcomes, and artifacts whose provenance can be
inspected end to end. Compared with naive prompting, the differences are
structural. Naive prompting produces unranked text with no selection principle,
no notion of a good-versus-bad reviewer, and no lineage; cogTIDE replaces each of
these with an explicit mechanism — blind peer review with peer prediction,
cross-run reviewer calibration, and stable-ID lineage — so that the *reasons* an
idea was promoted are recorded rather than implicit.

**What cogTIDE does not establish.** cogTIDE does not establish that any generated
theory is true, novel with respect to the existing literature, or empirically
viable. Its internal scores measure *relative review signal among model-generated
reviewers*; they are not measurements of scientific validity. Peer agreement
among LLM reviewers can be systematically biased in the same direction (for
example, toward elegance or familiar framing), so consensus in cogTIDE is not
consensus in a field. The generated content can also be hallucinated, out of
date, or subtly inconsistent, and it may misrepresent prior work.

**Risks of automation bias.** The chief hazard of a tool like this is that its
apparent rigor — scorecards, calibration weights, survival forecasts — lends
unearned authority to unvalidated ideas. A well-formatted score is still a model
opinion. We therefore treat responsible-use framing as a design requirement
rather than a disclaimer: cogTIDE labels its outputs as hypotheses for expert
review, states plainly that its scores are not truth signals, and keeps a full
audit trail precisely so that human experts can contest any promotion. Users
should subject every output to domain expertise, a proper literature review, and,
where relevant, preregistration and empirical testing before acting on it.

**Limitations.** Results depend heavily on the configured model and provider;
different endpoints and versions can yield materially different theories. Runs are
stochastic (temperature, sampling, retries), so repeating a run will not
reproduce identical outputs. A full run makes many LLM calls and can be slow and
expensive depending on provider and rate limits. TODO: discuss any observed
failure modes from real runs (e.g., decorative syntheses, umbrella theories,
role reassignment frequency).

## Materials and Methods

### Installation

cogTIDE requires **Python 3.10+**. Because prompts, configs, and schemas are
loaded relative to the repository root, an editable install from a clone is the
supported path:

```bash
git clone TODO:https://github.com/OWNER/CogTIDE.git
cd CogTIDE
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .                     # runtime
pip install -e ".[dev]"              # + test dependencies (pytest, pytest-asyncio)
```

Runtime dependencies are `openai>=1.40.0`, `pydantic>=2.5.0`, and `pyyaml>=6.0`
(see `pyproject.toml`).

### Configuration

Set the provider in `configs/models.yaml` (`api_base_url`, `model`, and the
key-holding environment-variable names). Provide the API key via the environment
or a repo-root `.env` (copy `.env.example`); the key value never lives in a config
file. Shell-exported variables take precedence over `.env`. Tune reliability in
`configs/retries.yaml` and stage/memory behavior in `configs/pipeline.yaml`.

### Pipeline invocation

```bash
# Full pipeline, Stage 0 -> Stage 4 (interactive Stage 0 gate):
python -m cogtide.cli run --topic "How does prior expectation shape perception?"
# Equivalent console script:
cogtide run --topic "..."
# Skip the Stage 0 confirmation gate (automation/CI):
cogtide run --topic "..." --non-interactive

# Stage by stage (Stage 0 prints a run_id that later stages resume):
cogtide stage_00 --topic "..."
cogtide stage_01 --resume <run_id>
cogtide stage_02 --resume <run_id>
cogtide stage_03 --resume <run_id>
cogtide stage_04 --resume <run_id>

# Resume Stages 2-4 on a run that already has Stage 0 + 1 artifacts:
cogtide resume_pipeline --resume <run_id>
```

To supply local materials to Stage 0, drop `.md`/`.txt`/`.rst` files into a
subfolder under `question/`; Stage 0 offers to ingest the best-matching folder by
simple token overlap with the question.

### Artifact schema

Every canonical artifact validates against a JSON Schema under `schemas/`,
including `question_dossier.schema.json`, `stage1_idea(.set).schema.json`,
`peer_review_envelope.schema.json`, `idea_scorecard.schema.json`,
`stage2_deep_theory(.set).schema.json`, `stage3_kernel(.set).schema.json`,
`stage4_theory(.set).schema.json`, `stage4_triplet.schema.json`,
`triplet_scorecard.schema.json`, `substage_manifest.schema.json`, and
`artifact_record.schema.json`. Schemas are exported from the pydantic models in
`cogtide/models/` via `scripts/export_schemas.py`. Run-level provenance lives in
`run_meta.json` and the append-only `artifacts.json`.

### Scoring formulas (as implemented)

Let a reviewed item receive reviews indexed by *r*. With `overall_quality` = the
reviewer's overall rating and `predicted_avg_quality` = the reviewer's prediction
of the average overall rating:

- quality_score = mean_r(overall_quality_r)
- unexpected_support = mean_r(overall_quality_r − predicted_avg_quality_r)
- survival_forecast = mean_r(predicted_survival_probability_r)
- calibration_weighted_score = Σ_r(w_r · overall_quality_r) / Σ_r(w_r), where
  w_r is the reviewer's calibration weight (falling back to the unweighted mean
  when no weights are available).

For a batch of ideas, `is_underrated` uses an adaptive threshold: the
`underrated_percentile` (default 0.75) of the run's own distribution of
unexpected-support values, floored at 0 (falling back to a fixed threshold, 0.5,
when the sample has fewer than four items). Single-item deep-theory and kernel
scorecards use the fixed threshold.

### Calibration formulas (as implemented)

For each reviewer, with `q_err` = mean absolute error between predicted and actual
average quality and `survival_accuracy` = fraction of survival predictions that
matched observed outcomes:

- quality_calibration = max(0, 1 − q_err / 5)   *(quality ratings are on a 1–10
  scale; the divisor rescales error toward [0, 1])*
- calibration_score = 0.5 · quality_calibration + 0.5 · survival_accuracy
- calibration_weight = 0.5 + 0.5 · calibration_score, i.e. clamped to
  [0.5, 1.0]

Better-calibrated reviewers thus earn up to twice the weight of the least
calibrated, and no reviewer is ever zeroed out. Across runs, records are merged
by count-weighted running averages of the error and accuracy terms, and the
calibration score and weight are recomputed from the merged terms.

### Determinism and seed caveats

Reviewer *selection* is seeded: eligible reviewers (those who did not author an
item) are shuffled with a per-item seed derived from a base seed and the item ID,
so reviewer-to-item assignment is reproducible given fixed inputs. The LLM
*outputs* are not deterministic — the shipped `temperature` is 1.0, providers
sample stochastically, and retries can alter timing — so repeating a run will not
reproduce identical theories or scores. For maximally comparable runs, pin the
model and provider, record `run_meta.json`, and (where the provider supports it)
lower the temperature; even then, exact reproduction is not guaranteed. TODO: if
a provider-side seed parameter is used in the demonstration run, document it here.

## Software Availability

- **Repository:** TODO: final public URL (e.g., `https://github.com/OWNER/CogTIDE`).
- **License:** MIT (see `LICENSE`).
- **Language:** Python 3.10+.
- **Dependencies:** `openai>=1.40.0`, `pydantic>=2.5.0`, `pyyaml>=6.0`; dev
  extras `pytest>=7.4.0`, `pytest-asyncio>=0.21.0`.
- **Install:** `pip install -e .` from a clone (editable install is the supported
  path).
- **Interfaces:** `python -m cogtide.cli` and the `cogtide` console script.

## Data Availability

cogTIDE bundles **no datasets**. Users supply their own research questions and,
optionally, local materials placed under `question/`. All example run artifacts
(`runs/<run_id>/…`) and cross-run memory (`memory/…`) are generated at runtime
and are git-ignored, since they may contain unpublished research material.
TODO: if a demonstration run's artifacts are released for the paper, deposit them
in an archive and cite the DOI here, with an explicit note that they are
unvalidated model outputs.

## Code Availability

The source code is available on GitHub: TODO: final repository URL. This paper
describes version **0.1.0**. TODO: mint an archival DOI (e.g., via Zenodo) for
the released version and cite it here.

## Funding

TODO: list funding sources and grant numbers, or state that the work received no
specific funding.

## Competing Interests

The authors declare no competing interests. TODO: confirm before submission and
disclose any relationships that could be perceived as competing interests.

## Acknowledgments

TODO: acknowledge colleagues, institutional support, and compute resources.
cogTIDE builds on the broader open-source LLM and scientific-Python ecosystems.

## References

We do not fabricate citations. The following are placeholders for the claims that
will need support; each names the intended work but omits authors/years/DOIs that
must be verified before submission.

1. TODO: add citation for Marr's three levels of analysis (Marr, *Vision*).
2. TODO: add citation for Tinbergen's four questions ("On aims and methods of
   ethology").
3. TODO: add citation for peer prediction / the Bayesian Truth Serum (Prelec and
   colleagues) as the conceptual basis of the peer-prediction and unexpected-
   support signals.
4. TODO: add citation(s) for scoring-rule / forecast-calibration theory
   underpinning survival forecasting and reviewer calibration (e.g., proper
   scoring rules; Brier score).
5. TODO: add citation(s) for the LLM research-idea / theory-generation literature
   (e.g., recent studies comparing LLM-generated and human research ideas).
6. TODO: add citation(s) for multi-agent / debate approaches to LLM reasoning and
   evaluation.
7. TODO: add citation(s) for LLM hallucination and overconfident fabrication.
8. TODO: add citation(s) for automation bias in decision support.
9. TODO: add citation for the OpenAI Python SDK / chat-completions API and for
   pydantic, as the primary software dependencies.
10. TODO: add any domain-specific references invoked by the demonstration run's
    question.

## Supporting Information

- **S1 Text. `HOW_IT_WORKS.md`** — an extended walkthrough of the scoring,
  calibration, and memory machinery.
- **S2 Data. JSON Schemas** — the canonical artifact schemas under `schemas/`
  (question dossier, ideas, peer-review envelope, scorecards, deep theories,
  kernels, theories/triplets, substage manifest, artifact record).
- **S3 Text. Example prompts** — the per-stage and shared prompt templates under
  `prompts/` (including the shared base contracts and the framework-aids prompt).
- **S4 Fig. Pipeline diagram** — `paper/figures/fig1_pipeline.mmd`.
- **S5 Fig. Scoring and calibration diagram** —
  `paper/figures/fig2_scoring_calibration.mmd`.
- **S6 Fig. Memory and artifact-lineage diagram** —
  `paper/figures/fig3_memory_artifact_loop.mmd`.
- **S7 Config. Reference configurations** — `configs/models.yaml`,
  `configs/retries.yaml`, `configs/pipeline.yaml`, and `configs/agents.yaml`.
