"""Stage 1: Expert Idea Generation.

Runs the fixed society of 19 domain experts sequentially (to respect
LLM-provider rate limits), each producing 3 ideas spanning risk levels
grounded → medium → bold. Ideas are canonicalized through
``STAGE1_IDEA_ALIASES`` and validated via ``Stage1Idea.from_normalized``.

After expert ideation, runs 2 challenger rounds over chunks of 10 ideas
and persists the raw critiques as side artifacts
``stage_01/challenges-round-<N>.json``. Challenges are informational
only in this build — they are not back-propagated into idea revisions.
The canonical Stage 1 artifact is
``stage_01/raw-ideas-<run_id>.json`` (matches controller glob).
"""

from __future__ import annotations

import json
from typing import Any

from cogtide.llm.canonicalization import (
    STAGE1_CHALLENGE_ALIASES,
    STAGE1_CHALLENGE_REQUIRED,
    STAGE1_IDEA_ALIASES,
    STAGE1_IDEA_REQUIRED,
    canonicalize,
)
from cogtide.llm.chunking import chunk_list
from cogtide.llm.prompt_builder import compose_with_shared
from cogtide.models import QuestionDossier, Stage1Idea, Stage1IdeaSet
from cogtide.pipeline.run_context import RunContext
from cogtide.registry import AgentSpec
from cogtide.utils.ids import idea_id as format_idea_id
from cogtide.utils.io import write_json

SHARED_BASES = [
    "BASE_reasoning.md",
    "BASE_json_contract.md",
    "BASE_output_contract.md",
    "BASE_preservation.md",
    "BASE_traceability.md",
]

STAGE_01_BASE = "stage_01/BASE_S01_expert_generation.md"
CHALLENGER_PROMPT_PATH = "stage_01/AG_S01_SS05_challenger.md"

DEFAULT_IDEAS_PER_EXPERT = 3
DEFAULT_CHALLENGER_ROUNDS = 2
DEFAULT_CHALLENGER_CHUNK_SIZE = 10
DEFAULT_EXPERT_RETRY_ATTEMPTS = 2


def _extract_items(parsed: Any) -> list[dict[str, Any]]:
    """Unwrap the expert/challenger response into a list of dicts.

    extract_json already unwraps common wrapper keys, but defend in
    depth: the model may still return a dict with a list-valued field.
    """
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        for key in ("ideas", "items", "results", "output"):
            v = parsed.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # Single-idea dict fallback.
        if any(
            k in parsed for k in ("title", "core_claim", "mechanism", "claim")
        ):
            return [parsed]
    return []


async def _call_expert(
    ctx: RunContext,
    spec: AgentSpec,
    question: str,
    background_context: str,
    *,
    attempt: int = 1,
    previous_failure_reasons: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Single expert call returning a list of raw idea dicts."""
    system_prompt = compose_with_shared(
        spec.prompt,
        SHARED_BASES,
        {"question": question, "background_context": background_context},
        stage_base=STAGE_01_BASE,
    )

    payload: dict[str, Any] = {
        "question": question,
        "background_context": background_context,
        "ideas_required": DEFAULT_IDEAS_PER_EXPERT,
        "attempt": attempt,
        "max_attempts": DEFAULT_EXPERT_RETRY_ATTEMPTS,
    }
    if attempt > 1 and previous_failure_reasons:
        payload["previous_response_was_invalid"] = True
        payload["previous_failure_reasons"] = previous_failure_reasons
        payload["instructions_for_retry"] = (
            "Re-emit exactly 3 ideas in grounded → medium → bold order. "
            "Every idea must have non-empty title, core_claim, mechanism, "
            "distinctive_prediction, why_interesting. Use the wrapper "
            '{"ideas": [...]}. Do not return placeholders.'
        )

    user_message = json.dumps(payload, ensure_ascii=False)

    parsed, record = await ctx.client.chat_json(
        agent_id=f"{spec.id}_attempt{attempt}",
        system_prompt=system_prompt,
        user_message=user_message,
        expect="auto",
    )

    if not record.succeeded:
        print(f"  [Stage 1] {spec.id} transport failed: {record.last_error}")
        return []

    return _extract_items(parsed)


async def run_expert(
    ctx: RunContext,
    spec: AgentSpec,
    question: str,
    background_context: str,
    *,
    start_idea_index: int,
) -> list[Stage1Idea]:
    """Run one expert with content-level retry. Returns 0..3 Stage1Ideas.

    Across retries we keep the best (largest valid) batch rather than
    overwriting a partially successful first attempt with an emptier retry.
    """
    max_attempts = DEFAULT_EXPERT_RETRY_ATTEMPTS
    previous_failure_reasons: list[str] = []
    best: list[Stage1Idea] = []
    source_lens = str(spec.extra.get("domain", spec.id))

    for attempt in range(1, max_attempts + 1):
        raw_items = await _call_expert(
            ctx, spec, question, background_context,
            attempt=attempt,
            previous_failure_reasons=previous_failure_reasons or None,
        )

        current: list[Stage1Idea] = []
        failure_reasons: list[str] = []

        for offset, raw in enumerate(raw_items[:DEFAULT_IDEAS_PER_EXPERT]):
            canonical, corrections = canonicalize(
                raw,
                aliases=STAGE1_IDEA_ALIASES,
                required=STAGE1_IDEA_REQUIRED,
            )
            missing = [c for c in corrections if c.startswith("missing/blank")]
            if missing:
                failure_reasons.append(
                    f"idea {offset + 1}: {'; '.join(missing)}"
                )
                continue

            idx = start_idea_index + len(current)
            iid = format_idea_id(idx)
            try:
                idea = Stage1Idea.from_normalized(
                    canonical, idea_id=iid, source_lens=source_lens
                )
            except Exception as e:
                failure_reasons.append(f"idea {offset + 1} pydantic: {e}")
                continue
            current.append(idea)

        if len(current) > len(best):
            best = current

        if len(best) >= DEFAULT_IDEAS_PER_EXPERT:
            break

        failure_reasons.append(
            f"received {len(current)}/{DEFAULT_IDEAS_PER_EXPERT} valid ideas"
        )
        previous_failure_reasons = failure_reasons
        if attempt < max_attempts:
            print(
                f"  [Stage 1] {spec.id} underfull ({len(current)}/"
                f"{DEFAULT_IDEAS_PER_EXPERT}); retrying"
            )

    if not best:
        print(
            f"  [Stage 1] {spec.id} produced 0 valid ideas after "
            f"{max_attempts} attempts"
        )
    return best


# ---------------------------------------------------------------------------
# Challenger
# ---------------------------------------------------------------------------

async def _call_challenger_chunk(
    ctx: RunContext,
    ideas: list[Stage1Idea],
    round_index: int,
    chunk_index: int,
) -> list[dict[str, Any]]:
    system_prompt = compose_with_shared(
        CHALLENGER_PROMPT_PATH,
        SHARED_BASES,
        {},
        stage_base=None,
    )

    payload = {
        "round_index": round_index,
        "chunk_index": chunk_index,
        "ideas": [i.model_dump() for i in ideas],
    }
    user_message = json.dumps(payload, ensure_ascii=False)

    parsed, record = await ctx.client.chat_json(
        agent_id=f"S01_challenger_r{round_index}_c{chunk_index}",
        system_prompt=system_prompt,
        user_message=user_message,
        expect="auto",
    )

    if not record.succeeded:
        print(f"  [Stage 1] challenger r{round_index}.c{chunk_index} failed")
        return []

    raw_items = _extract_items(parsed)
    cleaned: list[dict[str, Any]] = []
    for raw in raw_items:
        canonical, corrections = canonicalize(
            raw,
            aliases=STAGE1_CHALLENGE_ALIASES,
            required=STAGE1_CHALLENGE_REQUIRED,
        )
        if any(c.startswith("missing/blank") for c in corrections):
            continue
        cleaned.append(canonical)
    return cleaned


async def run_challenger_round(
    ctx: RunContext,
    ideas: list[Stage1Idea],
    round_index: int,
    *,
    chunk_size: int,
) -> list[dict[str, Any]]:
    chunks = chunk_list(ideas, chunk_size)
    all_critiques: list[dict[str, Any]] = []
    for ci, chunk in enumerate(chunks):
        critiques = await _call_challenger_chunk(ctx, chunk, round_index, ci)
        all_critiques.extend(critiques)
    return all_critiques


# ---------------------------------------------------------------------------
# Full Stage 1 orchestrator
# ---------------------------------------------------------------------------

async def run_stage_01(
    ctx: RunContext,
    dossier: QuestionDossier,
) -> Stage1IdeaSet:
    """Run complete Stage 1: 19-expert ideation + 2 challenger rounds."""
    stage_cfg = ctx.config.get("stages", {}).get("stage_01", {})
    challenger_rounds = int(
        stage_cfg.get("challenger_rounds", DEFAULT_CHALLENGER_ROUNDS)
    )
    chunk_size = int(
        stage_cfg.get(
            "challenger_chunk_size",
            ctx.config.get("batching", {}).get(
                "challenger_chunk_size", DEFAULT_CHALLENGER_CHUNK_SIZE
            ),
        )
    )

    experts = ctx.agents.for_substage("stage_01", "S01.03")
    experts = sorted(experts, key=lambda s: int(s.extra.get("expert_index", 0)))

    question = dossier.clarified_question or dossier.core_question
    background = dossier.background_context or dossier.consolidated_summary

    print(
        f"[Stage 1] Running {len(experts)} experts × "
        f"{DEFAULT_IDEAS_PER_EXPERT} ideas"
    )

    all_ideas: list[Stage1Idea] = []
    next_index = 1
    for spec in experts:
        print(f"  [Stage 1] expert {spec.id} ({spec.extra.get('domain', '?')})")
        produced = await run_expert(
            ctx, spec, question, background,
            start_idea_index=next_index,
        )
        all_ideas.extend(produced)
        next_index += len(produced)

    print(f"[Stage 1] Collected {len(all_ideas)} ideas before challenger")

    # Challenger rounds (side artifact only; ideas aren't mutated here).
    stage_dir = ctx.stage_dir("stage_01")
    for r in range(1, challenger_rounds + 1):
        print(f"[Stage 1] Challenger round {r} over chunks of {chunk_size}")
        critiques = await run_challenger_round(
            ctx, all_ideas, r, chunk_size=chunk_size
        )
        write_json(stage_dir / f"challenges-round-{r}.json", critiques)
        print(f"  collected {len(critiques)} critiques")

    expert_ids = [spec.extra.get("domain", spec.id) for spec in experts]
    idea_set = Stage1IdeaSet(
        ideas=all_ideas,
        expert_ids=[str(e) for e in expert_ids],
        challenger_round_count=challenger_rounds,
    )

    artifact_path = stage_dir / f"raw-ideas-{ctx.run_id}.json"
    write_json(artifact_path, idea_set.model_dump())
    print(f"[Stage 1] Wrote {len(all_ideas)} ideas to {artifact_path}")

    return idea_set
