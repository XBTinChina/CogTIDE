"""Stage 2: Peer-Screened Coalition Synthesis.

v2 flow:
  2A. Blind peer review of raw ideas → IdeaPeerReviewSet
  2B. Idea scorecard aggregation → IdeaScorecard per idea
  2C. Coalition construction using scorecards + v1 fairness logic
  2D. Drafter / critic within each coalition → candidate deep theory
  2E. External peer panel before final acceptance → DeepTheoryScorecard
  2F. Synthesis judge with peer scorecard → accept/reject

Stage 2 still outputs D01..D20 deep theories, but each comes with
a peer-prediction scorecard. Underfill is allowed if the quality
floor is not met.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from typing import Any

from cogtide.evaluation.peer_review import (
    run_idea_peer_review,
    run_theory_peer_panel,
)
from cogtide.evaluation.scoring import (
    compute_idea_scorecards,
    compute_theory_scorecard,
)
from cogtide.llm.canonicalization import (
    STAGE2_DEEP_THEORY_ALIASES,
    STAGE2_DEEP_THEORY_REQUIRED,
    STAGE2_DRAFT_ALIASES,
    STAGE2_DRAFT_REQUIRED,
)
from cogtide.llm.prompt_builder import compose_with_shared
from cogtide.llm.retry_wrapper import call_json_with_retry
from cogtide.memory import extract_keywords, retrieve_for_consumer
from cogtide.models.review_signals import IdeaPeerReviewSet, TheoryPeerReviewSet
from cogtide.models.scorecards import (
    DeepTheoryScorecard,
    IdeaScorecard,
)
from cogtide.models.stage1_idea import Stage1Idea, Stage1IdeaSet
from cogtide.models.stage2_deep_theory import (
    CoalitionAttempt,
    CoalitionMember,
    Stage2DeepTheory,
    Stage2DeepTheorySet,
)
from cogtide.pipeline.run_context import RunContext
from cogtide.utils.io import write_json

# Shared prompt bases used in all Stage 2 agent compositions
SHARED_BASES = [
    "BASE_reasoning.md",
    "BASE_json_contract.md",
    "BASE_output_contract.md",
    "BASE_preservation.md",
    "BASE_traceability.md",
]

# Default stage parameters (overridable via config/policy)
DEFAULT_TARGET_COUNT = 15
DEFAULT_COALITION_SIZE = 5
DEFAULT_MAX_ATTEMPTS = 25
DEFAULT_REVIEWERS_PER_IDEA = 5
DEFAULT_EXTERNAL_PANEL_SIZE = 5

# Generate up to ``target * pool_multiplier`` candidates so the post-loop
# top-K trim has a real distribution to rank against. 1.0 disables trimming.
DEFAULT_POOL_MULTIPLIER = 1.5

# Verdict allowlist — judge output must explicitly accept; ambiguous,
# missing, or paraphrased verdicts default to reject so the pipeline can
# never silently rubber-stamp a candidate.
_ACCEPT_TERMS = frozenset({
    "accept", "accepted",
    "approve", "approved",
    "pass", "passed",
    "yes", "true", "ok",
})


def _is_acceptance(d: dict) -> bool:
    raw = d.get("verdict", d.get("accepted", d.get("decision", "")))
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in _ACCEPT_TERMS


def _composite_peer_score(scorecard: DeepTheoryScorecard) -> float:
    """Composite ranking score for top-K trimming.

    Calibration-weighted quality (0–10 scale) plus a bounded bonus for
    positive unexpected_support so surprisingly strong theories edge out
    expected-quality peers without dominating the ranking. Theories with
    no reviews score 0 and sort to the bottom.
    """
    if scorecard.n_reviews <= 0:
        return 0.0
    base = scorecard.calibration_weighted_score or scorecard.quality_score
    bonus = max(0.0, scorecard.unexpected_support)
    return base + 0.5 * bonus


# ---------------------------------------------------------------------------
# 2A. Blind peer review of raw ideas
# ---------------------------------------------------------------------------

async def run_idea_screening(
    ctx: RunContext,
    ideas: list[Stage1Idea],
    expert_ids: list[str],
    *,
    n_reviewers: int = DEFAULT_REVIEWERS_PER_IDEA,
    seed: int = 42,
) -> IdeaPeerReviewSet:
    """Run blind peer reviews on all Stage 1 ideas."""
    idea_dicts = [i.model_dump() for i in ideas]

    system_prompt = compose_with_shared(
        "stage_02/AG_S02_peer_reviewer.md",
        SHARED_BASES,
        {},
        stage_base="stage_02/BASE_S02_coalition.md",
    )

    return await run_idea_peer_review(
        ctx.client,
        idea_dicts,
        expert_ids,
        n_reviewers_per_idea=n_reviewers,
        seed=seed,
        system_prompt=system_prompt,
        max_concurrency=ctx.client.retry_config.concurrency_limit,
    )


# ---------------------------------------------------------------------------
# 2B. Idea scorecard aggregation
# ---------------------------------------------------------------------------

def aggregate_idea_scorecards(
    review_set: IdeaPeerReviewSet,
    calibration_weights: dict[str, float] | None = None,
    source_lens_by_id: dict[str, str] | None = None,
) -> list[IdeaScorecard]:
    """Compute IdeaScorecard for every reviewed idea."""
    return compute_idea_scorecards(
        review_set,
        calibration_weights=calibration_weights,
        source_lens_by_id=source_lens_by_id,
    )


# ---------------------------------------------------------------------------
# 2C. Coalition construction (scorecard-enhanced)
# ---------------------------------------------------------------------------

def select_coalition(
    ideas: list[Stage1Idea],
    scorecards: dict[str, IdeaScorecard],
    used_idea_ids: set[str],
    used_expert_counts: Counter,
    *,
    coalition_size: int = DEFAULT_COALITION_SIZE,
    seed: int = 0,
    attempt_index: int = 0,
) -> list[tuple[Stage1Idea, IdeaScorecard]]:
    """Select a coalition of ideas + experts for one synthesis attempt.

    Selection objective: fairness + diversity + preservation +
    complementarity + peer signal.

    The selector prioritizes:
    1. Ideas not yet used in an accepted deep theory.
    2. Experts who have been under-represented.
    3. Ideas with preservation marks (UNIQUE, RISKY, SPECIAL).
    4. Ideas with high scorecard strength.
    5. Underrated ideas (high unexpected_support).
    6. Complementarity (diverse source lenses).
    """
    rng = random.Random(seed + attempt_index * 7919)

    # Build candidate pool: ideas not yet used
    pool = [i for i in ideas if i.id not in used_idea_ids]
    if len(pool) < coalition_size:
        # Allow reuse if pool exhausted
        pool = list(ideas)

    def _score(idea: Stage1Idea) -> float:
        sc = scorecards.get(idea.id)
        base = 0.0
        if sc:
            # Quality contributes positively
            base += sc.quality_score * 0.3
            # Unexpected support contributes positively (rescue underrated)
            base += max(0, sc.unexpected_support) * 0.25
            # Survival forecast contributes positively
            base += sc.survival_forecast * 5.0 * 0.15
            # Calibration-weighted score
            base += sc.calibration_weighted_score * 0.15

        # Under-represented expert bonus
        expert_uses = used_expert_counts.get(idea.source_lens, 0)
        base += max(0, 3 - expert_uses) * 0.5

        # Preservation mark bonus
        if idea.preservation_marks:
            base += 1.5

        # Underrated bonus
        if sc and sc.is_underrated:
            base += 1.0

        # Small random jitter for tie-breaking (deterministic)
        base += rng.random() * 0.1

        return base

    # Score and sort
    scored = sorted(pool, key=_score, reverse=True)

    # Greedily select ensuring lens diversity
    selected: list[tuple[Stage1Idea, IdeaScorecard]] = []
    selected_lenses: set[str] = set()

    for idea in scored:
        if len(selected) >= coalition_size:
            break
        # Prefer diverse lenses (allow duplicate only if needed)
        if idea.source_lens in selected_lenses and len(selected) < coalition_size - 1:
            # Skip if we still have room for diverse picks
            remaining_diverse = [
                i for i in scored
                if i.source_lens not in selected_lenses
                and i.id not in {s[0].id for s in selected}
            ]
            if remaining_diverse:
                continue
        sc = scorecards.get(idea.id, IdeaScorecard(idea_id=idea.id))
        selected.append((idea, sc))
        selected_lenses.add(idea.source_lens)

    return selected


# ---------------------------------------------------------------------------
# 2D. Drafter / critic within coalition
# ---------------------------------------------------------------------------

async def run_coalition_synthesis(
    ctx: RunContext,
    coalition: list[tuple[Stage1Idea, IdeaScorecard]],
    attempt_index: int,
    dossier_summary: str,
) -> tuple[dict[str, Any] | None, str]:
    """Run drafter + critic on a coalition to produce a candidate deep theory.

    Returns (candidate_dict_or_None, discussion_summary).
    """
    members = [
        CoalitionMember(expert_id=idea.source_lens, idea_id=idea.id)
        for idea, _ in coalition
    ]

    # Build idea packet with scorecard context
    idea_packet = []
    for idea, sc in coalition:
        entry = idea.model_dump()
        entry["peer_scorecard"] = {
            "quality": sc.quality_score,
            "unexpected_support": sc.unexpected_support,
            "survival_forecast": sc.survival_forecast,
            "is_underrated": sc.is_underrated,
        }
        idea_packet.append(entry)

    # Drafter phase
    drafter_prompt = compose_with_shared(
        "stage_02/AG_S02_drafter.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_02/BASE_S02_coalition.md",
    )

    drafter_payload = {
        "ideas": idea_packet,
        "coalition_members": [m.model_dump() for m in members],
        "attempt_index": attempt_index,
        "task": "synthesize_deep_theory",
    }

    draft_result, draft_record, draft_errors = await call_json_with_retry(
        ctx,
        agent_id=f"S02_drafter_attempt{attempt_index}",
        system_prompt=drafter_prompt,
        payload=drafter_payload,
        aliases=STAGE2_DRAFT_ALIASES,
        required=STAGE2_DRAFT_REQUIRED,
        expect="object",
    )

    if draft_result is None:
        return None, f"Drafter failed: {'; '.join(draft_errors)}"

    # Critic phase
    critic_prompt = compose_with_shared(
        "stage_02/AG_S02_critic.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_02/BASE_S02_coalition.md",
    )

    critic_payload = {
        "candidate": draft_result,
        "ideas": idea_packet,
        "coalition_members": [m.model_dump() for m in members],
        "task": "critique_and_revise",
    }

    revised, critic_record, critic_errors = await call_json_with_retry(
        ctx,
        agent_id=f"S02_critic_attempt{attempt_index}",
        system_prompt=critic_prompt,
        payload=critic_payload,
        aliases=STAGE2_DEEP_THEORY_ALIASES,
        required=STAGE2_DEEP_THEORY_REQUIRED,
        expect="object",
    )

    if revised is None:
        # Use draft if critic fails
        revised = draft_result

    discussion = (
        f"Draft: {draft_result.get('name', 'unnamed')}. "
        f"Critic revisions applied: {len(critic_errors) == 0}."
    )

    return revised, discussion


# ---------------------------------------------------------------------------
# 2E. External peer panel
# ---------------------------------------------------------------------------

async def run_external_panel_on_candidate(
    ctx: RunContext,
    candidate: dict[str, Any],
    coalition_expert_ids: set[str],
    all_expert_ids: list[str],
    *,
    panel_size: int = DEFAULT_EXTERNAL_PANEL_SIZE,
    seed: int = 0,
    calibration_weights: dict[str, float] | None = None,
) -> tuple[DeepTheoryScorecard, TheoryPeerReviewSet]:
    """Run an external peer panel on one candidate deep theory.

    Panelists are experts NOT in the coalition that produced it.
    Returns (scorecard, raw_review_set) so raw reviews can be persisted.
    """
    empty_reviews = TheoryPeerReviewSet(panel_kind="stage2_external")

    # Select panelists — strictly exclude coalition members
    eligible = [e for e in all_expert_ids if e not in coalition_expert_ids]
    if len(eligible) < panel_size:
        # Not enough external experts — this is a hard constraint.
        # Return an empty scorecard rather than weakening externality.
        return (
            DeepTheoryScorecard(deep_theory_id=candidate.get("id", "")),
            empty_reviews,
        )

    rng = random.Random(seed)
    rng.shuffle(eligible)
    panelists = eligible[:panel_size]

    system_prompt = compose_with_shared(
        "stage_02/AG_S02_external_reviewer.md",
        SHARED_BASES,
        {},
        stage_base="stage_02/BASE_S02_coalition.md",
    )

    review_set = await run_theory_peer_panel(
        ctx.client,
        [candidate],
        panelists,
        target_kind="deep_theory",
        system_prompt=system_prompt,
        max_concurrency=ctx.client.retry_config.concurrency_limit,
    )

    scorecard = compute_theory_scorecard(
        candidate.get("id", ""),
        review_set.reviews,
        calibration_weights=calibration_weights,
    )
    return scorecard, review_set


# ---------------------------------------------------------------------------
# 2F. Synthesis judge with peer scorecard
# ---------------------------------------------------------------------------

async def judge_candidate(
    ctx: RunContext,
    candidate: dict[str, Any],
    scorecard: DeepTheoryScorecard,
    coalition_members: list[CoalitionMember],
    attempt_index: int,
    dossier_summary: str,
    *,
    memory_context: str = "",
) -> tuple[bool, str]:
    """Judge accepts/rejects on synthesis quality alone.

    Acceptance rule:
    - Judge must pass (synthesis quality check) with an explicit
      acceptance verdict — ambiguous output rejects.
    - Traceability must pass (contributing ideas are real).

    Peer-score gating is deferred to a post-loop top-K trim in
    ``run_stage_02`` so floors are relative to this run's pool rather
    than fixed thresholds reviewers cluster above.
    """
    judge_prompt = compose_with_shared(
        "stage_02/AG_S02_judge.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_02/BASE_S02_coalition.md",
    )

    judge_payload = {
        "candidate": candidate,
        "coalition_members": [m.model_dump() for m in coalition_members],
        "peer_scorecard": {
            "quality_score": scorecard.quality_score,
            "unexpected_support": scorecard.unexpected_support,
            "survival_forecast": scorecard.survival_forecast,
            "calibration_weighted_score": scorecard.calibration_weighted_score,
            "is_underrated": scorecard.is_underrated,
            "reviewer_disagreement": scorecard.reviewer_disagreement,
        },
        "task": "judge_deep_theory",
        "memory_context": memory_context,
    }

    user_message = json.dumps(judge_payload, ensure_ascii=False)
    parsed, record = await ctx.client.chat_json(
        agent_id=f"S02_judge_attempt{attempt_index}",
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

    notes = parsed.get("judge_notes", parsed.get("notes", "accepted"))
    return True, str(notes)


# ---------------------------------------------------------------------------
# Full Stage 2 orchestrator
# ---------------------------------------------------------------------------

async def run_stage_02(
    ctx: RunContext,
    idea_set: Stage1IdeaSet,
    dossier_summary: str,
    *,
    target_count: int | None = None,
    coalition_size: int | None = None,
    max_attempts: int | None = None,
    seed: int = 42,
    calibration_weights: dict[str, float] | None = None,
) -> Stage2DeepTheorySet:
    """Run complete Stage 2: peer-screened coalition synthesis.

    1. Blind peer review all ideas.
    2. Compute idea scorecards.
    3. Loop: select coalition, synthesize, external panel, judge.
       Run until the judge-passed pool reaches ``target * pool_multiplier``
       (or ``max_attempts`` is exhausted).
    4. Trim the pool to top-``target`` by composite peer score.
    5. Return the kept deep theories with scorecards.
    """
    # Read config with defaults
    stage_cfg = ctx.config.get("stages", {}).get("stage_02", {})
    target = target_count or stage_cfg.get("target_deep_theory_count", DEFAULT_TARGET_COUNT)
    c_size = coalition_size or stage_cfg.get("coalition_size", DEFAULT_COALITION_SIZE)
    max_att = max_attempts or stage_cfg.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    n_reviewers = int(
        stage_cfg.get("reviewers_per_idea", DEFAULT_REVIEWERS_PER_IDEA)
    )
    pool_multiplier = float(
        stage_cfg.get("pool_multiplier", DEFAULT_POOL_MULTIPLIER)
    )
    needed_pool = min(max(target, int(round(target * pool_multiplier))), max_att)

    expert_ids = idea_set.expert_ids or sorted({i.source_lens for i in idea_set.ideas})

    print(f"[Stage 2] Starting peer-screened coalition synthesis")
    print(f"  Ideas: {len(idea_set.ideas)}, Experts: {len(expert_ids)}")
    print(
        f"  Target: {target}, Coalition size: {c_size}, "
        f"Max attempts: {max_att}, Reviewers/idea: {n_reviewers}, "
        f"Pool size before top-K trim: {needed_pool}"
    )

    memory_result = retrieve_for_consumer(
        ctx.config,
        stage="stage_02",
        consumer="synthesis_judge",
        question_keywords=extract_keywords(dossier_summary),
    )
    judge_memory_context = memory_result.rendered_context or ""
    if judge_memory_context:
        print(
            f"  Memory (synthesis_judge): {len(memory_result.selected_raw_memories)} "
            f"raw + {len(memory_result.selected_topic_memories)} topic records"
        )

    # 2A. Blind peer review
    print("[Stage 2] 2A: Running blind peer review of all ideas...")
    review_set = await run_idea_screening(
        ctx, idea_set.ideas, expert_ids,
        n_reviewers=n_reviewers, seed=seed,
    )
    expected_reviews = len(idea_set.ideas) * n_reviewers
    print(
        f"  Collected {len(review_set.reviews)}/{expected_reviews} reviews "
        f"({len(review_set.reviews) / expected_reviews:.0%})"
        if expected_reviews else f"  Collected {len(review_set.reviews)} reviews"
    )

    # Save review artifact
    stage_dir = ctx.stage_dir("stage_02")
    write_json(
        stage_dir / "idea-peer-reviews.json",
        review_set.model_dump(),
    )

    # Under-fill detection: find ideas that got fewer than n_reviewers
    # reviews (API failures dropped them). Warn loudly but don't abort —
    # downstream code handles missing/empty scorecards gracefully.
    review_counts: Counter[str] = Counter(
        r.target_id for r in review_set.reviews
    )
    underfull = [
        idea.id for idea in idea_set.ideas
        if review_counts.get(idea.id, 0) < n_reviewers
    ]
    zero_reviews = [
        idea.id for idea in idea_set.ideas
        if review_counts.get(idea.id, 0) == 0
    ]
    if underfull:
        preview = underfull[:10]
        tail = "…" if len(underfull) > 10 else ""
        print(
            f"  [WARN] {len(underfull)} ideas got <{n_reviewers} reviews "
            f"(likely API failures): {preview}{tail}"
        )
    if zero_reviews:
        print(
            f"  [WARN] {len(zero_reviews)} ideas got ZERO reviews — they "
            f"will have empty scorecards (quality=0) and only "
            f"preservation/fairness bonuses in coalition selection: "
            f"{zero_reviews[:10]}{'…' if len(zero_reviews) > 10 else ''}"
        )

    # 2B. Idea scorecard aggregation (with historical calibration if available)
    print("[Stage 2] 2B: Computing idea scorecards...")
    if calibration_weights:
        print(f"  Using historical calibration weights for {len(calibration_weights)} reviewers")
    scorecards_list = aggregate_idea_scorecards(
        review_set,
        calibration_weights=calibration_weights,
        source_lens_by_id={i.id: i.source_lens for i in idea_set.ideas},
    )
    scorecards = {sc.idea_id: sc for sc in scorecards_list}
    write_json(
        stage_dir / "idea-scorecards.json",
        [sc.model_dump() for sc in scorecards_list],
    )

    # Report top ideas
    top_ideas = sorted(scorecards_list, key=lambda s: s.quality_score, reverse=True)[:10]
    underrated = [s for s in scorecards_list if s.is_underrated]
    print(f"  Top idea quality: {top_ideas[0].quality_score if top_ideas else 0:.1f}")

    # unexpected_support distribution makes the adaptive threshold visible
    reviewed = [sc for sc in scorecards_list if sc.n_reviews > 0]
    if reviewed:
        us_sorted = sorted(sc.unexpected_support for sc in reviewed)
        median = us_sorted[len(us_sorted) // 2]
        p75_idx = min(int(len(us_sorted) * 0.75), len(us_sorted) - 1)
        p75 = us_sorted[p75_idx]
        print(
            f"  Unexpected-support distribution: "
            f"min={us_sorted[0]:+.2f}, median={median:+.2f}, "
            f"p75={p75:+.2f}, max={us_sorted[-1]:+.2f}"
        )
        print(
            f"  Underrated ideas: {len(underrated)}/{len(reviewed)} "
            f"(top quartile by unexpected_support, adaptive threshold)"
        )
    else:
        print(f"  Underrated ideas: {len(underrated)}")

    # 2C-2F: Coalition synthesis loop
    print("[Stage 2] 2C-2F: Starting coalition synthesis loop...")
    accepted_pairs: list[tuple[Stage2DeepTheory, DeepTheoryScorecard]] = []
    attempts: list[CoalitionAttempt] = []
    used_idea_ids: set[str] = set()
    used_expert_counts: Counter = Counter()
    deep_theory_counter = 0

    for attempt_idx in range(max_att):
        if len(accepted_pairs) >= needed_pool:
            break

        # 2C. Select coalition
        coalition = select_coalition(
            idea_set.ideas, scorecards, used_idea_ids, used_expert_counts,
            coalition_size=c_size, seed=seed, attempt_index=attempt_idx,
        )
        members = [
            CoalitionMember(expert_id=idea.source_lens, idea_id=idea.id)
            for idea, _ in coalition
        ]

        print(f"  Attempt {attempt_idx + 1}: coalition {[m.idea_id for m in members]}")

        attempt = CoalitionAttempt(
            attempt_index=attempt_idx,
            coalition_members=members,
        )

        # 2D. Drafter / critic
        candidate, discussion = await run_coalition_synthesis(
            ctx, coalition, attempt_idx, dossier_summary,
        )

        if candidate is None:
            attempt.rejection_reason = discussion
            attempts.append(attempt)
            print(f"    → Synthesis failed: {discussion[:80]}")
            continue

        attempt.candidate_name = candidate.get("name", "")
        attempt.candidate_statement = candidate.get("deep_theory_statement", candidate.get("statement", ""))[:300]
        attempt.discussion_summary = discussion

        # Assign temporary ID for panel review
        deep_theory_counter += 1
        temp_id = f"D{deep_theory_counter:02d}"
        candidate["id"] = temp_id

        # 2E. External peer panel
        coalition_experts = {m.expert_id for m in members}
        scorecard, panel_reviews = await run_external_panel_on_candidate(
            ctx, candidate, coalition_experts, expert_ids,
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

        # 2F. Judge with scorecard
        accepted_flag, judge_notes = await judge_candidate(
            ctx, candidate, scorecard, members, attempt_idx, dossier_summary,
            memory_context=judge_memory_context,
        )

        if accepted_flag:
            # Build preserved marks from contributing ideas
            preserved = []
            for idea, _ in coalition:
                preserved.extend(idea.preservation_marks)

            dt = Stage2DeepTheory.from_normalized(
                candidate,
                deep_theory_id=temp_id,
                coalition_members=members,
                judge_notes=judge_notes,
                preserved_marks=preserved,
            )
            # Attach peer scorecard
            dt.peer_quality_score = scorecard.quality_score
            dt.peer_unexpected_support = scorecard.unexpected_support
            dt.peer_survival_forecast = scorecard.survival_forecast
            dt.peer_calibration_weighted_score = scorecard.calibration_weighted_score
            dt.peer_reviewer_disagreement = scorecard.reviewer_disagreement
            dt.peer_is_underrated = scorecard.is_underrated

            accepted_pairs.append((dt, scorecard))
            attempt.accepted = True
            attempt.accepted_deep_theory_id = temp_id

            # Track usage
            for idea, _ in coalition:
                used_idea_ids.add(idea.id)
                used_expert_counts[idea.source_lens] += 1

            print(f"    → Accepted {temp_id}: {dt.name}")
        else:
            attempt.rejection_reason = judge_notes
            print(f"    → Rejected: {judge_notes[:80]}")

        attempts.append(attempt)

    # Top-K trim: rank judge-passed candidates by composite peer score and
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

        trimmed_ids = {dt.id for dt, _ in trimmed}
        trimmed_scores = {dt.id: _composite_peer_score(sc) for dt, sc in trimmed}
        for att in attempts:
            if att.accepted_deep_theory_id in trimmed_ids:
                ts = trimmed_scores[att.accepted_deep_theory_id]
                att.accepted = False
                att.rejection_reason = (
                    f"Trimmed by top-{target} peer-score selection: "
                    f"{ts:.2f} below cutoff {cutoff:.2f}"
                )
                att.accepted_deep_theory_id = ""
        accepted_pairs = kept
        print(
            f"[Stage 2] Top-K trim: kept {len(kept)}/{len(ranked)} "
            f"(cutoff composite score {cutoff:.2f})"
        )

    accepted = [dt for dt, _ in accepted_pairs]
    result = Stage2DeepTheorySet(
        deep_theories=accepted,
        attempts=attempts,
        target_count=target,
    )

    # Save canonical artifact
    artifact_path = stage_dir / f"coalition-deep-theories-{ctx.run_id}.json"
    write_json(artifact_path, result.model_dump())

    print(f"[Stage 2] Complete: {len(accepted)}/{target} deep theories accepted "
          f"in {len(attempts)} attempts")

    return result
