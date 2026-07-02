"""Stage 4: Peer-Calibrated Triplet Elaboration.

v2 flow:
  4A. Constructor + reviser build core / solid / risky (same as v1).
  4B. External peer panel scores each variant separately.
  4C. Final triplet selection rule using operational definitions:
      - Core = highest balanced score across quality dimensions.
      - Solid = highest robustness/defensibility above minimum novelty.
      - Risky = highest breakthrough-potential above minimum coherence.

So triplets become peer-calibrated theory profiles, not just
local elaboration formats.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from cogtide.evaluation.peer_review import (
    run_triplet_peer_panel,
)
from cogtide.evaluation.scoring import compute_triplet_scorecard
from cogtide.llm.prompt_builder import compose_with_shared
from cogtide.models.review_signals import TripletPeerReview
from cogtide.models.scorecards import TripletScorecard
from cogtide.models.stage3_kernel import Stage3Kernel, Stage3KernelSet
from cogtide.models.stage4_theory import (
    Stage4Theory,
    Stage4TheorySet,
    Stage4Triplet,
    TripletRole,
)
from cogtide.pipeline.run_context import RunContext
from cogtide.utils.ids import slugify, theory_id as make_theory_id
from cogtide.utils.io import write_json, write_text
from cogtide.reporting.stage4_markdown import (
    render_stage4_kernel_markdown,
    render_stage4_markdown,
)

SHARED_BASES = [
    "BASE_reasoning.md",
    "BASE_json_contract.md",
    "BASE_output_contract.md",
    "BASE_preservation.md",
    "BASE_traceability.md",
]

DEFAULT_REVISION_ROUNDS = 2
DEFAULT_PANEL_SIZE = 5
DEFAULT_TRIPLET_MAX_ATTEMPTS = 3
# Three full theories with 14 detailed fields each easily exceed the
# global 8192-token default; per-attempt schedule grows the output
# budget so a truncated first try can recover on retry. The first-
# attempt budget is intentionally modest (~12k) to keep TPM pressure
# low on rate-limited providers; we only escalate to 24k/48k when the
# model actually truncates.
DEFAULT_TRIPLET_MAX_TOKENS_SCHEDULE: tuple[int, ...] = (12000, 24000, 48000)
# Plain-language explainer is a single per-kernel call; output is
# small (kernel background + analogy + per-variant glossaries) so a
# generous fixed budget is enough.
DEFAULT_EXPLAINER_MAX_TOKENS: int = 16000


# ---------------------------------------------------------------------------
# Triplet-shaped retry helper
# ---------------------------------------------------------------------------

async def _call_triplet_json_with_retry(
    ctx: RunContext,
    *,
    agent_id: str,
    system_prompt: str,
    base_payload: dict[str, Any],
    max_attempts: int = DEFAULT_TRIPLET_MAX_ATTEMPTS,
    max_tokens_schedule: tuple[int, ...] = DEFAULT_TRIPLET_MAX_TOKENS_SCHEDULE,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Call an LLM that should return ``{core, solid, risky}``.

    Retries when the transport succeeds but the response doesn't parse
    as a dict with three non-empty role dicts. On each retry, the prior
    failure reason is fed back to the model so it can correct the shape,
    and the per-call ``max_tokens`` budget grows so a truncated first
    attempt can recover.

    Also performs a single outer retry on rate-limit-class transport
    failures (HTTP 429, some providers' proprietary rate-limit codes such
    as 1302, ``RateLimitError``): the inner
    client's 5 retries can exhaust well within one TPM window, so we
    sleep ~75s and retry once at the smallest scheduled budget so the
    per-minute token bucket has a chance to refill.

    Returns ``(parsed_triplet, errors)``. ``parsed_triplet`` is ``None``
    on total failure; ``errors`` always carries the diagnostic trail.
    """
    errors: list[str] = []
    # One-shot outer cooldown for rate-limit-class transport failures:
    # the inner client already burns its 5 retries against 429s, so a
    # further retry only helps if we actually wait long enough for the
    # provider's per-minute window to reset and shrink our token bill.
    rl_cooldown_used = False
    forced_next_max_tokens: int | None = None
    for attempt in range(1, max_attempts + 1):
        payload = dict(base_payload)
        payload["attempt"] = attempt
        payload["max_attempts"] = max_attempts
        if attempt > 1 and errors:
            payload["previous_response_was_invalid"] = True
            payload["previous_failure_reasons"] = errors[-3:]
            payload["instructions_for_retry"] = (
                "Your previous response could not be used. Re-emit a "
                "single JSON object with exactly three top-level keys: "
                "'core', 'solid', 'risky'. Each value must itself be a "
                "JSON object containing the full theory fields (name, "
                "statement, central_claim, ontology, mechanism, "
                "formal_sketch, boundary_conditions, main_assumptions, "
                "distinctive_predictions, testable_predictions, "
                "falsifiers, measurement_strategy, phenomena_explained, "
                "open_questions). Do NOT wrap the result in an array. "
                "Do NOT wrap it in a container key like 'triplet', "
                "'theories', or 'response'."
            )
        # Grow the output budget per attempt; clamp to the last value
        # in the schedule so a long retry tail still uses the largest.
        # The cooldown retry overrides this with a smaller budget so we
        # don't immediately re-burn the same TPM that just got us 429'd.
        if forced_next_max_tokens is not None:
            attempt_max_tokens = forced_next_max_tokens
            forced_next_max_tokens = None
        else:
            mt_idx = min(attempt - 1, len(max_tokens_schedule) - 1)
            attempt_max_tokens = max_tokens_schedule[mt_idx]
        user_message = json.dumps(payload, ensure_ascii=False)
        parsed, record = await ctx.client.chat_json(
            agent_id=(
                f"{agent_id}_attempt{attempt}" if attempt > 1 else agent_id
            ),
            system_prompt=system_prompt,
            user_message=user_message,
            expect="object",
            max_tokens=attempt_max_tokens,
            timeout_override=600.0,
        )

        if not record.succeeded:
            err_msg = record.last_error or ""
            is_rate_limit_class = (
                "RateLimitError" in err_msg
                or "429" in err_msg
                or "1302" in err_msg
                or "rate limit" in err_msg.lower()
            )
            if (
                is_rate_limit_class
                and not rl_cooldown_used
                and attempt < max_attempts
            ):
                rl_cooldown_used = True
                forced_next_max_tokens = max_tokens_schedule[0]
                cooldown_seconds = 75.0
                errors.append(
                    f"attempt {attempt}: transport failure (rate-limit class): "
                    f"{record.last_error}; cooling down "
                    f"{cooldown_seconds:.0f}s before one retry at "
                    f"max_tokens={forced_next_max_tokens}"
                )
                print(
                    f"  [outer-cooldown] {agent_id} rate-limit-class failure; "
                    f"sleeping {cooldown_seconds:.0f}s before retry at "
                    f"max_tokens={forced_next_max_tokens}..."
                )
                await asyncio.sleep(cooldown_seconds)
                continue
            errors.append(
                f"attempt {attempt}: transport failure: {record.last_error}"
            )
            return None, errors

        # If the provider stopped because we hit the output cap, the
        # JSON is almost certainly truncated. Surface that explicitly
        # so the diagnostic trail names the real cause; the next
        # attempt will use a larger budget from the schedule.
        truncated = record.was_truncated

        if not isinstance(parsed, dict):
            snippet = str(parsed)[:150] if parsed is not None else "(none)"
            cause = (
                "response truncated at max_tokens "
                f"(budget={attempt_max_tokens}, finish_reason={record.finish_reason!r})"
                if truncated
                else f"parsed output is not a dict (type={type(parsed).__name__}, snippet={snippet!r})"
            )
            errors.append(f"attempt {attempt}: {cause}")
            continue

        missing_roles = [
            r for r in ("core", "solid", "risky")
            if not isinstance(parsed.get(r), dict) or not parsed.get(r)
        ]
        if missing_roles:
            cause = (
                f"response truncated at max_tokens before completing roles "
                f"{missing_roles} "
                f"(budget={attempt_max_tokens}, got keys={list(parsed.keys())[:8]})"
                if truncated
                else (
                    f"triplet missing/empty roles {missing_roles}; "
                    f"got keys={list(parsed.keys())[:8]}"
                )
            )
            errors.append(f"attempt {attempt}: {cause}")
            continue

        return parsed, errors

    return None, errors


# ---------------------------------------------------------------------------
# 4A. Constructor + reviser
# ---------------------------------------------------------------------------

async def construct_triplet(
    ctx: RunContext,
    kernel: Stage3Kernel,
    expert_ids: list[str],
    theory_counter: int,
    dossier_summary: str,
    *,
    max_tokens_schedule: tuple[int, ...] = DEFAULT_TRIPLET_MAX_TOKENS_SCHEDULE,
) -> tuple[list[dict[str, Any]], str]:
    """Build initial core / solid / risky variants from a kernel.

    Returns (list of 3 theory dicts, panel_notes).
    """
    constructor_prompt = compose_with_shared(
        "stage_04/AG_S04_constructor.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_04/BASE_S04_triplet.md",
    )

    kernel_data = kernel.model_dump()
    kernel_data["peer_scorecard"] = {
        "quality": kernel.peer_quality_score,
        "unexpected_support": kernel.peer_unexpected_support,
        "survival_forecast": kernel.peer_survival_forecast,
        "is_underrated": kernel.peer_is_underrated,
    }

    base_payload = {
        "kernel": kernel_data,
        "panel_expert_ids": expert_ids,
        "task": "construct_triplet",
        "instructions": (
            "Build three theory variants from this kernel:\n"
            "- core: the most balanced, well-supported version.\n"
            "- solid: the most defensible/robust version (high coherence + defensibility).\n"
            "- risky: the highest-upside version (novel + potentially transformative).\n"
            "Return an object with keys 'core', 'solid', 'risky', each containing "
            "the full theory fields."
        ),
    }

    parsed, errors = await _call_triplet_json_with_retry(
        ctx,
        agent_id=f"S04_constructor_{kernel.id}",
        system_prompt=constructor_prompt,
        base_payload=base_payload,
        max_tokens_schedule=max_tokens_schedule,
    )

    if parsed is None:
        reason = "; ".join(errors[-3:]) if errors else "unknown"
        return [], f"Constructor failed after retries: {reason}"

    variants = []
    for role in ("core", "solid", "risky"):
        var_data = dict(parsed[role])
        var_data["role"] = role
        var_data["parent_kernel"] = kernel.id
        variants.append(var_data)

    notes = parsed.get("panel_notes", parsed.get("notes", ""))
    return variants, str(notes)


async def revise_triplet(
    ctx: RunContext,
    kernel: Stage3Kernel,
    variants: list[dict[str, Any]],
    revision_round: int,
    dossier_summary: str,
    *,
    max_tokens_schedule: tuple[int, ...] = DEFAULT_TRIPLET_MAX_TOKENS_SCHEDULE,
) -> list[dict[str, Any]]:
    """Run one revision round on the triplet.

    Revision is best-effort: on total failure we log and return the
    prior variants unchanged (so a bad revision round doesn't destroy
    progress), but the failure is no longer silent.
    """
    reviser_prompt = compose_with_shared(
        "stage_04/AG_S04_reviser.md",
        SHARED_BASES,
        {"dossier_summary": dossier_summary},
        stage_base="stage_04/BASE_S04_triplet.md",
    )

    base_payload = {
        "kernel": {"id": kernel.id, "name": kernel.name,
                   "kernel_statement": kernel.kernel_statement},
        "current_triplet": {
            "core": variants[0] if len(variants) > 0 else {},
            "solid": variants[1] if len(variants) > 1 else {},
            "risky": variants[2] if len(variants) > 2 else {},
        },
        "revision_round": revision_round,
        "task": "revise_triplet",
    }

    parsed, errors = await _call_triplet_json_with_retry(
        ctx,
        agent_id=f"S04_reviser_{kernel.id}_round{revision_round}",
        system_prompt=reviser_prompt,
        base_payload=base_payload,
        max_tokens_schedule=max_tokens_schedule,
    )

    if parsed is None:
        reason = "; ".join(errors[-2:]) if errors else "unknown"
        print(
            f"    [WARN] revision round {revision_round} for {kernel.id} "
            f"failed, keeping prior variants: {reason}"
        )
        return variants

    revised = []
    for role in ("core", "solid", "risky"):
        var_data = parsed.get(role, {})
        if not isinstance(var_data, dict) or not var_data:
            idx = {"core": 0, "solid": 1, "risky": 2}[role]
            var_data = dict(variants[idx]) if idx < len(variants) else {}
        else:
            var_data = dict(var_data)
        var_data["role"] = role
        var_data["parent_kernel"] = kernel.id
        revised.append(var_data)

    return revised


# ---------------------------------------------------------------------------
# 4A.5. Plain-language explainer (kernel background + analogy + glossary)
# ---------------------------------------------------------------------------

def _empty_explainer() -> dict[str, Any]:
    """Default explainer payload used when the LLM call fails or is
    skipped. The renderer treats empty fields as "no plain-language
    section available" rather than printing placeholders."""
    role_blank = {
        "plain_summary": "",
        "plain_analogy": "",
        "glossary": [],
        "why_this_role": "",
    }
    return {
        "kernel_background": "",
        "kernel_analogy": "",
        "triplet_overview": "",
        "core": dict(role_blank),
        "solid": dict(role_blank),
        "risky": dict(role_blank),
    }


def _coerce_explainer_payload(parsed: Any) -> dict[str, Any]:
    """Coerce the explainer LLM output into the renderer-ready shape.

    Missing keys fall back to their empty defaults; per-role objects
    are normalised so the renderer never has to guess. We never raise
    here — the explainer is best-effort and a partial result is still
    useful.
    """
    out = _empty_explainer()
    if not isinstance(parsed, dict):
        return out

    for top_key in ("kernel_background", "kernel_analogy", "triplet_overview"):
        v = parsed.get(top_key, "")
        if isinstance(v, str):
            out[top_key] = v.strip()

    for role in ("core", "solid", "risky"):
        block = parsed.get(role)
        if not isinstance(block, dict):
            continue
        role_out = out[role]
        for k in ("plain_summary", "plain_analogy", "why_this_role"):
            v = block.get(k, "")
            if isinstance(v, str):
                role_out[k] = v.strip()
        glossary_raw = block.get("glossary", [])
        glossary: list[dict[str, str]] = []
        if isinstance(glossary_raw, list):
            for entry in glossary_raw:
                if not isinstance(entry, dict):
                    continue
                term = str(entry.get("term", "")).strip()
                plain = str(entry.get("plain", entry.get("definition", ""))).strip()
                if term and plain:
                    glossary.append({"term": term, "plain": plain})
        role_out["glossary"] = glossary

    return out


async def explain_triplet(
    ctx: RunContext,
    kernel: Stage3Kernel,
    triplet: Stage4Triplet,
    *,
    max_tokens: int = DEFAULT_EXPLAINER_MAX_TOKENS,
) -> dict[str, Any]:
    """Run a single LLM pass to produce plain-language framing for one
    triplet: kernel background, analogy, per-variant plain summaries,
    and per-variant glossaries.

    Best-effort: on transport failure or unparseable output we return
    the empty-explainer payload and let the renderer skip the
    plain-language sections, rather than blocking the whole stage on
    a non-essential pass.
    """
    explainer_prompt = compose_with_shared(
        "stage_04/AG_S04_explainer.md",
        SHARED_BASES,
        {},
        stage_base="stage_04/BASE_S04_triplet.md",
    )

    def _theory_payload(t: Stage4Theory) -> dict[str, Any]:
        return {
            "id": t.id,
            "role": t.role,
            "name": t.name,
            "statement": t.statement,
            "central_claim": t.central_claim,
            "ontology": list(t.ontology),
            "mechanism": t.mechanism,
            "formal_sketch": t.formal_sketch,
            "boundary_conditions": list(t.boundary_conditions),
            "main_assumptions": list(t.main_assumptions),
            "distinctive_predictions": list(t.distinctive_predictions),
            "testable_predictions": list(t.testable_predictions),
            "falsifiers": list(t.falsifiers),
            "measurement_strategy": list(t.measurement_strategy),
            "phenomena_explained": list(t.phenomena_explained),
            "open_questions": list(t.open_questions),
        }

    payload = {
        "task": "explain_triplet",
        "kernel": {
            "id": kernel.id,
            "name": kernel.name,
            "kernel_statement": kernel.kernel_statement,
            "deeper_substrate": kernel.deeper_substrate,
            "rationale": kernel.rationale,
            "mechanism_sketch": kernel.mechanism_sketch,
            "key_predictions": list(kernel.key_predictions),
            "key_assumptions": list(kernel.key_assumptions),
            "preserved_tensions": kernel.preserved_tensions,
        },
        "triplet": {
            "core": _theory_payload(triplet.core_theory),
            "solid": _theory_payload(triplet.solid_theory),
            "risky": _theory_payload(triplet.risky_theory),
        },
    }

    try:
        parsed, record = await ctx.client.chat_json(
            agent_id=f"S04_explainer_{kernel.id}",
            system_prompt=explainer_prompt,
            user_message=json.dumps(payload, ensure_ascii=False),
            expect="object",
            max_tokens=max_tokens,
        )
    except Exception as e:
        print(
            f"    [WARN] explainer for {kernel.id} raised "
            f"{type(e).__name__}: {e}; skipping plain-language section"
        )
        return _empty_explainer()

    if not record.succeeded:
        print(
            f"    [WARN] explainer for {kernel.id} failed: "
            f"{record.last_error}; skipping plain-language section"
        )
        return _empty_explainer()

    if record.was_truncated:
        print(
            f"    [WARN] explainer for {kernel.id} truncated at "
            f"max_tokens={max_tokens}; using whatever parsed cleanly"
        )

    return _coerce_explainer_payload(parsed)


# ---------------------------------------------------------------------------
# 4B. External peer panel on finished triplet
# ---------------------------------------------------------------------------

async def run_triplet_external_panel(
    ctx: RunContext,
    kernel: Stage3Kernel,
    variants: list[dict[str, Any]],
    theory_ids: dict[str, str],
    all_expert_ids: list[str],
    *,
    panel_size: int = DEFAULT_PANEL_SIZE,
    seed: int = 0,
) -> tuple[list[TripletPeerReview], TripletScorecard]:
    """Run external peer panel on a finished triplet.

    Panelists are drawn from the full 19-expert society but strictly
    exclude experts who served on this kernel's council.
    Returns (reviews, scorecard) so raw reviews can be persisted.
    """
    import random

    council_experts = set(kernel.council_expert_ids)

    # Strictly exclude council members; draw from full expert pool
    eligible = [e for e in all_expert_ids if e not in council_experts]
    if len(eligible) < panel_size:
        # Not enough truly external experts — return empty rather than
        # weakening the outside-evaluator principle
        return [], TripletScorecard(parent_kernel=kernel.id)

    rng = random.Random(seed)
    rng.shuffle(eligible)
    panelists = eligible[:panel_size]

    system_prompt = compose_with_shared(
        "stage_04/AG_S04_triplet_reviewer.md",
        SHARED_BASES,
        {},
        stage_base="stage_04/BASE_S04_triplet.md",
    )

    triplet_data = {
        "parent_kernel": kernel.id,
        "core": variants[0] if len(variants) > 0 else {},
        "solid": variants[1] if len(variants) > 1 else {},
        "risky": variants[2] if len(variants) > 2 else {},
    }

    reviews = await run_triplet_peer_panel(
        ctx.client,
        triplet_data,
        panelists,
        system_prompt=system_prompt,
        max_concurrency=ctx.client.retry_config.concurrency_limit,
    )

    scorecard = compute_triplet_scorecard(
        kernel.id, reviews, theory_ids=theory_ids,
    )

    return reviews, scorecard


# ---------------------------------------------------------------------------
# 4C. Final triplet selection and assembly
# ---------------------------------------------------------------------------

def finalize_triplet(
    kernel: Stage3Kernel,
    variants: list[dict[str, Any]],
    scorecard: TripletScorecard,
    theory_ids: dict[str, str],
    panel_expert_ids: list[str],
    revision_rounds: int,
) -> Stage4Triplet:
    """Finalize triplet with peer-calibrated role assignment.

    If the scorecard indicates roles should be reassigned, the actual
    variant data is swapped into the new roles — not just recorded
    as metadata. This means the theory labeled "core" in the final
    artifact genuinely has the highest balanced score, etc.
    """
    # Original positional mapping: variants[0]=core, [1]=solid, [2]=risky
    original_role_to_idx = {"core": 0, "solid": 1, "risky": 2}
    # Map from original theory_id -> variant index
    tid_to_idx: dict[str, int] = {}
    for role, idx in original_role_to_idx.items():
        tid_to_idx[theory_ids[role]] = idx

    # Determine which variant data goes into each final role.
    # If reassigned, the scorecard tells us which original theory_id
    # should fill each role.
    if scorecard.roles_reassigned and scorecard.assigned_core_id:
        core_idx = tid_to_idx.get(scorecard.assigned_core_id, 0)
        solid_idx = tid_to_idx.get(scorecard.assigned_solid_id, 1)
        risky_idx = tid_to_idx.get(scorecard.assigned_risky_id, 2)
    else:
        core_idx, solid_idx, risky_idx = 0, 1, 2

    def _safe_variant(idx: int) -> dict:
        return variants[idx] if idx < len(variants) else {}

    def _build_theory(var_data: dict, role: TripletRole, tid: str) -> Stage4Theory:
        vs = next(
            (v for v in scorecard.variant_scores if v.theory_id == tid),
            # Fall back to matching by role if the ID doesn't match
            # (can happen when the scorecard assigned a different ID)
            next(
                (v for v in scorecard.variant_scores if v.variant_role == role),
                None,
            ),
        )
        t = Stage4Theory.from_normalized(
            var_data,
            theory_id=tid,
            role=role,
            parent_kernel=kernel.id,
        )
        if vs:
            t.peer_coherence = vs.coherence
            t.peer_defensibility = vs.defensibility
            t.peer_novelty = vs.novelty
            t.peer_distinctiveness = vs.distinctiveness
            t.peer_experimental_fertility = vs.experimental_fertility
            t.peer_upside_if_true = vs.upside_if_true
            t.peer_balanced_score = vs.balanced_score
        t.role_confirmed_by_peers = not scorecard.roles_reassigned
        return t

    core_theory = _build_theory(
        _safe_variant(core_idx), "core", theory_ids["core"],
    )
    solid_theory = _build_theory(
        _safe_variant(solid_idx), "solid", theory_ids["solid"],
    )
    risky_theory = _build_theory(
        _safe_variant(risky_idx), "risky", theory_ids["risky"],
    )

    return Stage4Triplet(
        parent_kernel=kernel.id,
        panel_expert_ids=panel_expert_ids,
        core_theory=core_theory,
        solid_theory=solid_theory,
        risky_theory=risky_theory,
        revision_rounds_used=revision_rounds,
        roles_reassigned=scorecard.roles_reassigned,
        reassignment_rationale=scorecard.reassignment_rationale,
        peer_review_panel_ids=scorecard.reviewer_ids,
    )


# ---------------------------------------------------------------------------
# Full Stage 4 orchestrator
# ---------------------------------------------------------------------------

async def run_stage_04(
    ctx: RunContext,
    kernel_set: Stage3KernelSet,
    dossier_summary: str,
    *,
    revision_rounds: int | None = None,
    seed: int = 42,
    all_expert_ids: list[str] | None = None,
) -> Stage4TheorySet:
    """Run complete Stage 4: peer-calibrated triplet elaboration.

    For each kernel:
    1. Constructor builds core / solid / risky.
    2. Reviser refines over N rounds.
    3. External peer panel scores each variant.
    4. Operational definitions assign final roles.
    """
    stage_cfg = ctx.config.get("stages", {}).get("stage_04", {})
    rev_rounds = revision_rounds or stage_cfg.get("revision_rounds", DEFAULT_REVISION_ROUNDS)
    raw_schedule = stage_cfg.get(
        "triplet_max_tokens_schedule", DEFAULT_TRIPLET_MAX_TOKENS_SCHEDULE
    )
    triplet_mt_schedule: tuple[int, ...] = tuple(int(x) for x in raw_schedule) or (
        DEFAULT_TRIPLET_MAX_TOKENS_SCHEDULE
    )
    explainer_enabled = bool(stage_cfg.get("explainer_enabled", True))
    explainer_max_tokens = int(
        stage_cfg.get("explainer_max_tokens", DEFAULT_EXPLAINER_MAX_TOKENS)
    )

    # Build the full expert pool for external panels
    if all_expert_ids is None:
        all_expert_ids = sorted({
            eid
            for k in kernel_set.kernels
            for eid in k.contributing_expert_ids
        })

    print(f"[Stage 4] Starting peer-calibrated triplet elaboration")
    print(f"  Kernels: {len(kernel_set.kernels)}, Revision rounds: {rev_rounds}")
    print(f"  External panel pool: {len(all_expert_ids)} experts")
    print(f"  Triplet max_tokens schedule: {triplet_mt_schedule}")
    print(f"  Plain-language explainer: {'on' if explainer_enabled else 'off'}")

    all_theories: list[Stage4Theory] = []
    all_triplets: list[Stage4Triplet] = []
    kernel_doc_links: list[tuple[Stage3Kernel, Stage4Triplet, str]] = []
    theory_counter = 0

    for kernel in kernel_set.kernels:
        print(f"  Processing kernel {kernel.id}: {kernel.name}")

        # Assign theory IDs for this triplet
        theory_counter += 1
        core_tid = make_theory_id(theory_counter * 3 - 2)
        solid_tid = make_theory_id(theory_counter * 3 - 1)
        risky_tid = make_theory_id(theory_counter * 3)
        tids = {"core": core_tid, "solid": solid_tid, "risky": risky_tid}

        # 4A. Constructor
        constructor_expert_cap = int(stage_cfg.get("expert_max", 7))
        expert_ids = kernel.council_expert_ids[:constructor_expert_cap]
        variants, panel_notes = await construct_triplet(
            ctx, kernel, expert_ids, theory_counter, dossier_summary,
            max_tokens_schedule=triplet_mt_schedule,
        )

        if not variants:
            print(f"    → Construction failed: {panel_notes[:200]}")
            continue

        # 4A continued: revision rounds
        for r in range(rev_rounds):
            variants = await revise_triplet(
                ctx, kernel, variants, r + 1, dossier_summary,
                max_tokens_schedule=triplet_mt_schedule,
            )

        # 4B. External peer panel (drawn from full expert pool)
        reviews, scorecard = await run_triplet_external_panel(
            ctx, kernel, variants, tids, all_expert_ids,
            panel_size=int(
                stage_cfg.get("external_panel_size", DEFAULT_PANEL_SIZE)
            ),
            seed=seed + theory_counter,
        )

        # Save raw triplet peer reviews and scorecard
        stage_dir = ctx.stage_dir("stage_04")
        if reviews:
            write_json(
                stage_dir / f"triplet-peer-reviews-{kernel.id}.json",
                [r.model_dump() for r in reviews],
            )
        write_json(
            stage_dir / f"triplet-scorecard-{kernel.id}.json",
            scorecard.model_dump(),
        )

        # 4C. Finalize with operational definitions
        triplet = finalize_triplet(
            kernel, variants, scorecard, tids, expert_ids, rev_rounds,
        )

        all_theories.extend([
            triplet.core_theory,
            triplet.solid_theory,
            triplet.risky_theory,
        ])
        all_triplets.append(triplet)

        # 4D. Plain-language explainer + per-kernel markdown.
        # The explainer is best-effort; if it returns the empty
        # payload the renderer simply skips the plain-language
        # sections so the technical document is still produced.
        if explainer_enabled:
            explainer = await explain_triplet(
                ctx, kernel, triplet, max_tokens=explainer_max_tokens,
            )
        else:
            explainer = _empty_explainer()

        kernel_slug = slugify(kernel.name)
        explainer_path = (
            stage_dir / f"kernel-{kernel.id}-{kernel_slug}-explainer.json"
        )
        write_json(explainer_path, explainer)

        kernel_md_filename = f"kernel-{kernel.id}-{kernel_slug}.md"
        kernel_md_path = stage_dir / kernel_md_filename
        write_text(
            kernel_md_path,
            render_stage4_kernel_markdown(
                triplet=triplet,
                kernel=kernel,
                explainer=explainer,
                run_id=ctx.run_id,
            ),
        )
        kernel_doc_links.append((kernel, triplet, kernel_md_filename))

        reassign_note = ""
        if scorecard.roles_reassigned:
            reassign_note = f" (roles reassigned: {scorecard.reassignment_rationale[:60]})"
        print(
            f"    → Triplet complete: {core_tid}/{solid_tid}/{risky_tid}"
            f"{reassign_note}; wrote {kernel_md_filename}"
        )

    result = Stage4TheorySet(
        theories=all_theories,
        triplets=all_triplets,
    )

    stage_dir = ctx.stage_dir("stage_04")
    artifact_path = stage_dir / f"triplet-theories-{ctx.run_id}.json"
    write_json(artifact_path, result.model_dump())

    markdown_path = stage_dir / f"triplet-theories-{ctx.run_id}.md"
    write_text(
        markdown_path,
        render_stage4_markdown(
            result,
            run_id=ctx.run_id,
            kernel_doc_links=[
                (k.id, k.name, fname) for (k, _t, fname) in kernel_doc_links
            ],
        ),
    )

    print(f"[Stage 4] Complete: {len(all_triplets)} triplets, "
          f"{len(all_theories)} theories")
    print(
        f"  Artifacts: {artifact_path.name}, {markdown_path.name}, "
        f"{len(kernel_doc_links)} per-kernel markdown files"
    )

    return result
