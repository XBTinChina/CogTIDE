"""Stage 3: Peer-Scored Council Synthesis.

v2 flow:
  3A. Council selection uses Stage 2 scorecards (peer support,
      unexpected support, downstream survival forecast, lineage diversity).
  3B. Council discussion (structurally similar to v1: restatement,
      bridges, negotiation, shared substrate, attack/defense, finalize).
  3C. External kernel peer panel (outside experts rate + predict).
  3D. Kernel judge with peer panel output → accept/reject.

Stage 3 still outputs K01..K05 kernels, each with a peer scorecard.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from typing import Any

from cogtide.evaluation.peer_review import (
    run_theory_peer_panel,
)
from cogtide.evaluation.scoring import compute_kernel_scorecard
from cogtide.llm.canonicalization import (
    STAGE3_KERNEL_ALIASES,
    STAGE3_KERNEL_REQUIRED,
)
from cogtide.llm.prompt_builder import compose_with_shared
from cogtide.llm.retry_wrapper import call_json_with_retry
from cogtide.memory import extract_keywords, retrieve_for_consumer
from cogtide.models.review_signals import TheoryPeerReviewSet
from cogtide.models.scorecards import KernelScorecard
from cogtide.models.stage2_deep_theory import Stage2DeepTheory, Stage2DeepTheorySet
from cogtide.models.stage3_kernel import (
    CouncilAttempt,
    Stage3Kernel,
    Stage3KernelSet,
)
from cogtide.pipeline.run_context import RunContext
from cogtide.reporting.stage3_markdown import render_stage3_markdown
from cogtide.utils.io import write_json, write_text

SHARED_BASES = [
    "BASE_reasoning.md",
    "BASE_json_contract.md",
    "BASE_output_contract.md",
    "BASE_preservation.md",
    "BASE_traceability.md",
]

DEFAULT_TARGET_KERNEL_COUNT = 5
DEFAULT_COUNCIL_THEORY_SIZE = 3
DEFAULT_EXPERT_MIN = 5
DEFAULT_EXPERT_MAX = 7
DEFAULT_MAX_ATTEMPTS = 12
DEFAULT_EXTERNAL_PANEL_SIZE = 5

# Generate up to ``target * pool_multiplier`` candidates so the post-loop
# top-K trim has a real distribution to rank against. 1.0 disables trimming.
DEFAULT_POOL_MULTIPLIER = 1.5

_ACCEPT_TERMS = frozenset({
    "accept", "accepted",
    "approve", "approved",
    "pass", "passed",
    "yes", "true", "ok",
})


def _composite_peer_score(scorecard: KernelScorecard) -> float:
    """Composite ranking score for top-K trimming.

    Calibration-weighted quality (0–10 scale) plus a bounded bonus for
    positive unexpected_support. Kernels with no reviews score 0 and
    sort to the bottom.
    """
    if scorecard.n_reviews <= 0:
        return 0.0
    base = scorecard.calibration_weighted_score or scorecard.quality_score
    bonus = max(0.0, scorecard.unexpected_support)
    return base + 0.5 * bonus


# ---------------------------------------------------------------------------
# 3A. Council selection using Stage 2 scorecards
# ---------------------------------------------------------------------------

def select_council(
    deep_theories: list[Stage2DeepTheory],
    used_theory_ids: set[str],
    used_expert_counts: Counter,
    all_expert_ids: list[str],
    *,
    theory_size: int = DEFAULT_COUNCIL_THEORY_SIZE,
    expert_min: int = DEFAULT_EXPERT_MIN,
    expert_max: int = DEFAULT_EXPERT_MAX,
    seed: int = 0,
    attempt_index: int = 0,
) -> tuple[list[Stage2DeepTheory], list[str]]:
    """Select a council of deep theories + experts.

    Score each deep theory using Stage 2 peer support, unexpected
    support, downstream survival forecast, and lineage diversity.
    """
    rng = random.Random(seed + attempt_index * 6271)

    # Pool: prefer unused theories
    pool = [dt for dt in deep_theories if dt.id not in used_theory_ids]
    if len(pool) < theory_size:
        pool = list(deep_theories)

    def _theory_score(dt: Stage2DeepTheory) -> float:
        score = 0.0
        # Peer quality from Stage 2
        score += dt.peer_quality_score * 0.3
        # Unexpected support: theories that surprised reviewers positively
        score += max(0, dt.peer_unexpected_support) * 0.25
        # Survival forecast
        score += dt.peer_survival_forecast * 5.0 * 0.2
        # Lineage diversity: theories with more diverse contributing experts
        score += len(dt.contributing_expert_ids) * 0.1
        # Underrated bonus
        if dt.peer_is_underrated:
            score += 1.0
        # Preservation bonus
        if dt.preserved_marks:
            score += 0.5
        # Under-used bonus
        if dt.id not in used_theory_ids:
            score += 1.0
        # Jitter
        score += rng.random() * 0.1
        return score

    scored = sorted(pool, key=_theory_score, reverse=True)

    # Greedily select ensuring lineage diversity
    selected_theories: list[Stage2DeepTheory] = []
    selected_idea_sets: list[set[str]] = []

    for dt in scored:
        if len(selected_theories) >= theory_size:
            break
        # Check lineage diversity: don't pick theories that share too many ideas
        dt_ideas = set(dt.contributing_idea_ids)
        overlap_ok = all(
            len(dt_ideas & existing) <= 1
            for existing in selected_idea_sets
        )
        if not overlap_ok and len(selected_theories) < theory_size - 1:
            continue
        selected_theories.append(dt)
        selected_idea_sets.append(dt_ideas)

    # Select council experts: union of contributing experts + fill to min
    council_experts: set[str] = set()
    for dt in selected_theories:
        council_experts.update(dt.contributing_expert_ids)

    # Fill up to expert_min with under-represented experts. Stop at
    # expert_min (not expert_max): over-filling small councils shrinks
    # the pool of non-council experts eligible for the external panel.
    if len(council_experts) < expert_min:
        remaining = [e for e in all_expert_ids if e not in council_experts]
        remaining.sort(key=lambda e: (used_expert_counts.get(e, 0), rng.random()))
        for e in remaining:
            if len(council_experts) >= expert_min:
                break
            council_experts.add(e)

    # Trim if over expert_max
    expert_list = sorted(council_experts)
    if len(expert_list) > expert_max:
        expert_list = expert_list[:expert_max]

    return selected_theories, expert_list


# ---------------------------------------------------------------------------
# 3B. Council discussion
# ---------------------------------------------------------------------------

async def run_council_discussion(
    ctx: RunContext,
    theories: list[Stage2DeepTheory],
    expert_ids: list[str],
    attempt_index: int,
    dossier_summary: str,
) -> tuple[dict[str, Any] | None, str]:
    """Run structured council discussion to find a shared deeper substrate.

    Keeps the v1 rhythm: restatement, bridges, negotiation, shared
    substrate search, attack and defense, finalize or fail.
    """
    facilitator_prompt = compose_with_shared(
        "stage_03/AG_S03_facilitator.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_03/BASE_S03_council.md",
    )

    # Build theory packet with peer scores
    theory_packet = []
    for dt in theories:
        entry = dt.model_dump()
        entry["peer_scorecard"] = {
            "quality": dt.peer_quality_score,
            "unexpected_support": dt.peer_unexpected_support,
            "survival_forecast": dt.peer_survival_forecast,
            "is_underrated": dt.peer_is_underrated,
        }
        theory_packet.append(entry)

    payload = {
        "theories": theory_packet,
        "council_expert_ids": expert_ids,
        "attempt_index": attempt_index,
        "task": "find_deeper_substrate",
    }

    result, record, errors = await call_json_with_retry(
        ctx,
        agent_id=f"S03_facilitator_attempt{attempt_index}",
        system_prompt=facilitator_prompt,
        payload=payload,
        aliases=STAGE3_KERNEL_ALIASES,
        required=STAGE3_KERNEL_REQUIRED,
        expect="object",
    )

    if result is None:
        return None, f"Facilitator failed: {'; '.join(errors)}"

    discussion = result.get("discussion_summary", "Council discussion completed.")
    return result, discussion


# ---------------------------------------------------------------------------
# 3C. External kernel peer panel
# ---------------------------------------------------------------------------

async def run_kernel_peer_panel(
    ctx: RunContext,
    candidate: dict[str, Any],
    council_expert_ids: set[str],
    all_expert_ids: list[str],
    *,
    panel_size: int = DEFAULT_EXTERNAL_PANEL_SIZE,
    seed: int = 0,
    calibration_weights: dict[str, float] | None = None,
) -> tuple[KernelScorecard, TheoryPeerReviewSet]:
    """Run an external peer panel on one candidate kernel.

    Panelists are experts NOT in the council that produced it.
    Returns (scorecard, raw_review_set) so raw reviews can be persisted.
    """
    empty_reviews = TheoryPeerReviewSet(panel_kind="stage3_external")

    # Strictly exclude council members
    eligible = [e for e in all_expert_ids if e not in council_expert_ids]
    if len(eligible) < panel_size:
        return (
            KernelScorecard(kernel_id=candidate.get("id", "")),
            empty_reviews,
        )

    rng = random.Random(seed)
    rng.shuffle(eligible)
    panelists = eligible[:panel_size]

    system_prompt = compose_with_shared(
        "stage_03/AG_S03_external_reviewer.md",
        SHARED_BASES,
        {},
        stage_base="stage_03/BASE_S03_council.md",
    )

    review_set = await run_theory_peer_panel(
        ctx.client,
        [candidate],
        panelists,
        target_kind="kernel",
        system_prompt=system_prompt,
        max_concurrency=ctx.client.retry_config.concurrency_limit,
    )

    scorecard = compute_kernel_scorecard(
        candidate.get("id", ""),
        review_set.reviews,
        calibration_weights=calibration_weights,
    )
    return scorecard, review_set


# ---------------------------------------------------------------------------
# 3D. Kernel judge (peer-aware)
# ---------------------------------------------------------------------------

async def judge_kernel(
    ctx: RunContext,
    candidate: dict[str, Any],
    scorecard: KernelScorecard,
    council_theories: list[Stage2DeepTheory],
    council_expert_ids: list[str],
    attempt_index: int,
    dossier_summary: str,
    *,
    memory_context: str = "",
) -> tuple[bool, str]:
    """Peer-aware kernel judge.

    Asks the v1 questions:
    - Deeper than inputs?
    - Not just an average?
    - Distinct?
    - Tension-preserving?
    - Traceable?

    Plus v2 questions:
    - Genuinely supported by outsiders?
    - Only locally persuasive?
    - Surprisingly strong relative to expectations?

    Numerical peer-score gating is deferred to a post-loop top-K trim in
    ``run_stage_03``. Only the categorical "locally persuasive only" flag
    remains as a hard veto here.
    """
    judge_prompt = compose_with_shared(
        "stage_03/AG_S03_judge.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_03/BASE_S03_council.md",
    )

    judge_payload = {
        "candidate": candidate,
        "council_deep_theory_ids": [dt.id for dt in council_theories],
        "council_expert_ids": council_expert_ids,
        "peer_scorecard": {
            "quality_score": scorecard.quality_score,
            "unexpected_support": scorecard.unexpected_support,
            "survival_forecast": scorecard.survival_forecast,
            "calibration_weighted_score": scorecard.calibration_weighted_score,
            "is_underrated": scorecard.is_underrated,
            "reviewer_disagreement": scorecard.reviewer_disagreement,
            "is_locally_persuasive_only": scorecard.is_locally_persuasive_only,
            "is_genuinely_deep": scorecard.is_genuinely_deep,
        },
        "task": "judge_kernel",
        "memory_context": memory_context,
    }

    # Default to REJECT when the verdict is ambiguous/missing. Any
    # non-explicit acceptance (wrong field, truncated output, synonym we
    # don't recognize) is treated as a rejection so the pipeline cannot
    # silently rubber-stamp everything.
    def _is_acceptance(d: dict) -> bool:
        raw = d.get("verdict", d.get("accepted", d.get("decision", "")))
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in _ACCEPT_TERMS

    user_message = json.dumps(judge_payload, ensure_ascii=False)
    parsed, record = await ctx.client.chat_json(
        agent_id=f"S03_judge_attempt{attempt_index}",
        system_prompt=judge_prompt,
        user_message=user_message,
        expect="object",
    )

    if not record.succeeded or not isinstance(parsed, dict):
        return False, f"Judge call failed: {record.last_error}"

    if not _is_acceptance(parsed):
        raw_verdict = parsed.get(
            "verdict", parsed.get("accepted", parsed.get("decision", ""))
        )
        reason = parsed.get(
            "rejection_reason",
            parsed.get(
                "reason",
                f"verdict not explicitly accepted (got {raw_verdict!r})",
            ),
        )
        return False, str(reason)

    # Categorical panel veto (kept as a hard reject — distinct from
    # numerical peer floors, which are now handled by the post-loop
    # top-K trim in run_stage_03).
    if scorecard.is_locally_persuasive_only:
        return False, "Kernel flagged as locally persuasive only by external panel"

    notes = parsed.get("judge_notes", parsed.get("notes", "accepted"))
    return True, str(notes)


# ---------------------------------------------------------------------------
# Full Stage 3 orchestrator
# ---------------------------------------------------------------------------

async def run_stage_03(
    ctx: RunContext,
    deep_theory_set: Stage2DeepTheorySet,
    dossier_summary: str,
    *,
    target_count: int | None = None,
    max_attempts: int | None = None,
    seed: int = 42,
    calibration_weights: dict[str, float] | None = None,
) -> Stage3KernelSet:
    """Run complete Stage 3: peer-scored council synthesis.

    1. For each council attempt:
       a. Select council (3 deep theories + 5-7 experts) using scorecards.
       b. Run council discussion.
       c. External peer panel on candidate kernel.
       d. Peer-aware judge accepts/rejects on synthesis quality (and
          the categorical "locally persuasive only" veto).
    2. Loop until the judge-passed pool reaches ``target * pool_multiplier``
       (or ``max_attempts`` is exhausted).
    3. Trim the pool to top-``target`` by composite peer score.
    4. Return the kept kernels with scorecards.
    """
    stage_cfg = ctx.config.get("stages", {}).get("stage_03", {})
    target = target_count or stage_cfg.get("target_kernel_count", DEFAULT_TARGET_KERNEL_COUNT)
    max_att = max_attempts or stage_cfg.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    theory_size = stage_cfg.get("council_theory_size", DEFAULT_COUNCIL_THEORY_SIZE)
    expert_min = stage_cfg.get("expert_min", DEFAULT_EXPERT_MIN)
    expert_max = stage_cfg.get("expert_max", DEFAULT_EXPERT_MAX)
    pool_multiplier = float(
        stage_cfg.get("pool_multiplier", DEFAULT_POOL_MULTIPLIER)
    )
    needed_pool = min(max(target, int(round(target * pool_multiplier))), max_att)

    deep_theories = deep_theory_set.deep_theories
    all_expert_ids = sorted({
        eid for dt in deep_theories for eid in dt.contributing_expert_ids
    })

    print(f"[Stage 3] Starting peer-scored council synthesis")
    print(
        f"  Deep theories: {len(deep_theories)}, Target kernels: {target}, "
        f"Pool size before top-K trim: {needed_pool}"
    )
    if calibration_weights:
        print(f"  Using calibration weights for {len(calibration_weights)} reviewers")

    memory_result = retrieve_for_consumer(
        ctx.config,
        stage="stage_03",
        consumer="kernel_judge",
        question_keywords=extract_keywords(dossier_summary),
    )
    judge_memory_context = memory_result.rendered_context or ""
    if judge_memory_context:
        print(
            f"  Memory (kernel_judge): {len(memory_result.selected_raw_memories)} "
            f"raw + {len(memory_result.selected_topic_memories)} topic records"
        )

    stage_dir = ctx.stage_dir("stage_03")
    accepted_pairs: list[tuple[Stage3Kernel, KernelScorecard]] = []
    attempts: list[CouncilAttempt] = []
    used_theory_ids: set[str] = set()
    used_expert_counts: Counter = Counter()
    kernel_counter = 0

    for attempt_idx in range(max_att):
        if len(accepted_pairs) >= needed_pool:
            break

        # 3A. Select council
        council_theories, council_experts = select_council(
            deep_theories, used_theory_ids, used_expert_counts,
            all_expert_ids,
            theory_size=theory_size,
            expert_min=expert_min,
            expert_max=expert_max,
            seed=seed,
            attempt_index=attempt_idx,
        )

        theory_ids = [dt.id for dt in council_theories]
        print(f"  Attempt {attempt_idx + 1}: council {theory_ids}")

        attempt = CouncilAttempt(
            attempt_index=attempt_idx,
            council_deep_theory_ids=theory_ids,
            council_expert_ids=council_experts,
        )

        # 3B. Council discussion
        candidate, discussion = await run_council_discussion(
            ctx, council_theories, council_experts, attempt_idx, dossier_summary,
        )

        if candidate is None:
            attempt.rejection_reason = discussion
            attempts.append(attempt)
            print(f"    → Discussion failed: {discussion[:80]}")
            continue

        attempt.candidate_name = candidate.get("name", "")
        attempt.candidate_statement = candidate.get("kernel_statement", candidate.get("statement", ""))[:300]
        attempt.discussion_summary = discussion

        # Assign temporary ID
        kernel_counter += 1
        temp_id = f"K{kernel_counter:02d}"
        candidate["id"] = temp_id

        # 3C. External peer panel
        council_set = set(council_experts)
        scorecard, panel_reviews = await run_kernel_peer_panel(
            ctx, candidate, council_set, all_expert_ids,
            panel_size=int(
                stage_cfg.get("external_panel_size", DEFAULT_EXTERNAL_PANEL_SIZE)
            ),
            seed=seed + attempt_idx,
            calibration_weights=calibration_weights,
        )

        # Persist raw external panel reviews
        if panel_reviews.reviews:
            write_json(
                stage_dir / f"external-panel-reviews-{temp_id}.json",
                panel_reviews.model_dump(),
            )

        # 3D. Judge
        accepted_flag, judge_notes = await judge_kernel(
            ctx, candidate, scorecard, council_theories,
            council_experts, attempt_idx, dossier_summary,
            memory_context=judge_memory_context,
        )

        if accepted_flag:
            # Collect lineage
            contributing_idea_ids = sorted({
                iid for dt in council_theories for iid in dt.contributing_idea_ids
            })
            contributing_expert_ids = sorted({
                eid for dt in council_theories for eid in dt.contributing_expert_ids
            })
            preserved_marks = []
            for dt in council_theories:
                preserved_marks.extend(dt.preserved_marks)

            kernel = Stage3Kernel.from_normalized(
                candidate,
                kernel_id=temp_id,
                contributing_deep_theory_ids=theory_ids,
                council_expert_ids=council_experts,
                contributing_idea_ids=contributing_idea_ids,
                contributing_expert_ids=contributing_expert_ids,
                preserved_marks=preserved_marks,
                judge_notes=judge_notes,
            )
            # Attach peer scorecard
            kernel.peer_quality_score = scorecard.quality_score
            kernel.peer_unexpected_support = scorecard.unexpected_support
            kernel.peer_survival_forecast = scorecard.survival_forecast
            kernel.peer_calibration_weighted_score = scorecard.calibration_weighted_score
            kernel.peer_reviewer_disagreement = scorecard.reviewer_disagreement
            kernel.peer_is_underrated = scorecard.is_underrated
            kernel.peer_is_locally_persuasive_only = scorecard.is_locally_persuasive_only

            accepted_pairs.append((kernel, scorecard))
            attempt.accepted = True
            attempt.accepted_kernel_id = temp_id

            for dt in council_theories:
                used_theory_ids.add(dt.id)
            for eid in council_experts:
                used_expert_counts[eid] += 1

            print(f"    → Accepted {temp_id}: {kernel.name}")
        else:
            attempt.rejection_reason = judge_notes
            print(f"    → Rejected: {judge_notes[:80]}")

        attempts.append(attempt)

    # Top-K trim: rank judge-passed kernels by composite peer score and
    # keep the top ``target``. Trimmed entries flip their attempt record
    # to rejected so the audit trail reflects the final outcome.
    if len(accepted_pairs) > target:
        ranked = sorted(
            accepted_pairs,
            key=lambda pair: _composite_peer_score(pair[1]),
            reverse=True,
        )
        kept = ranked[:target]
        trimmed = ranked[target:]
        cutoff = _composite_peer_score(kept[-1][1])

        trimmed_ids = {k.id for k, _ in trimmed}
        trimmed_scores = {k.id: _composite_peer_score(sc) for k, sc in trimmed}
        for att in attempts:
            if att.accepted_kernel_id in trimmed_ids:
                ts = trimmed_scores[att.accepted_kernel_id]
                att.accepted = False
                att.rejection_reason = (
                    f"Trimmed by top-{target} peer-score selection: "
                    f"{ts:.2f} below cutoff {cutoff:.2f}"
                )
                att.accepted_kernel_id = ""
        accepted_pairs = kept
        print(
            f"[Stage 3] Top-K trim: kept {len(kept)}/{len(ranked)} "
            f"(cutoff composite score {cutoff:.2f})"
        )

    accepted = [k for k, _ in accepted_pairs]
    result = Stage3KernelSet(
        kernels=accepted,
        attempts=attempts,
        target_count=target,
    )

    artifact_path = stage_dir / f"council-kernels-{ctx.run_id}.json"
    write_json(artifact_path, result.model_dump())

    markdown_path = stage_dir / f"council-kernels-{ctx.run_id}.md"
    write_text(markdown_path, render_stage3_markdown(result, run_id=ctx.run_id))

    print(f"[Stage 3] Complete: {len(accepted)}/{target} kernels accepted "
          f"in {len(attempts)} attempts")
    print(f"  Artifacts: {artifact_path.name}, {markdown_path.name}")

    return result
