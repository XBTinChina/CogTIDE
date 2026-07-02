"""Top-level pipeline controller. Sequences Stage 0 through Stage 4.

v2 extends the controller with peer-prediction orchestration:
- After Stage 1, runs blind peer review + scorecard computation.
- Stage 2 uses peer-screened coalition synthesis.
- Stage 3 uses peer-scored council synthesis.
- Stage 4 uses peer-calibrated triplet elaboration.
- After Stage 4, compiles calibration memory for self-improvement.
"""

from __future__ import annotations

from cogtide.models import (
    QuestionDossier,
    Stage1IdeaSet,
    Stage2DeepTheorySet,
    Stage3KernelSet,
    Stage4TheorySet,
    IdeaPeerReviewSet,
)
from cogtide.models.scorecards import IdeaScorecard
from cogtide.pipeline.run_context import RunContext
from cogtide.utils.io import read_json


def load_dossier_from_run(ctx: RunContext) -> QuestionDossier:
    """Resume helper: read the canonical Stage 0 artifact off disk.

    Stage 0 writes timestamped ``question-<slug>-<ts>.json`` files, so a
    Stage 0 re-run can leave several candidates in the same run dir;
    take the latest by name (the timestamp suffix sorts lexicographically).
    """
    stage_dir = ctx.stage_dir("stage_00")
    candidates = list(stage_dir.glob("question-*.json"))
    if not candidates:
        raise FileNotFoundError(f"No Stage 0 dossier in {stage_dir}")
    latest = max(candidates, key=lambda p: p.name)
    return QuestionDossier.model_validate(read_json(latest))


def load_idea_set_from_run(ctx: RunContext) -> Stage1IdeaSet:
    stage_dir = ctx.stage_dir("stage_01")
    candidates = list(stage_dir.glob("raw-ideas-*.json"))
    if not candidates:
        raise FileNotFoundError(f"No Stage 1 artifact in {stage_dir}")
    return Stage1IdeaSet.model_validate(read_json(candidates[0]))


def load_idea_peer_reviews_from_run(ctx: RunContext) -> IdeaPeerReviewSet | None:
    """Load the Stage 2 blind peer review artifact if it exists."""
    stage_dir = ctx.stage_dir("stage_02")
    path = stage_dir / "idea-peer-reviews.json"
    if not path.exists():
        return None
    return IdeaPeerReviewSet.model_validate(read_json(path))


def load_idea_scorecards_from_run(ctx: RunContext) -> list[IdeaScorecard]:
    """Load the Stage 2 idea scorecards if they exist."""
    stage_dir = ctx.stage_dir("stage_02")
    path = stage_dir / "idea-scorecards.json"
    if not path.exists():
        return []
    data = read_json(path)
    if not isinstance(data, list):
        return []
    return [IdeaScorecard.model_validate(d) for d in data]


def load_deep_theory_set_from_run(ctx: RunContext) -> Stage2DeepTheorySet:
    stage_dir = ctx.stage_dir("stage_02")
    candidates = list(stage_dir.glob("coalition-deep-theories-*.json"))
    if not candidates:
        raise FileNotFoundError(f"No Stage 2 artifact in {stage_dir}")
    return Stage2DeepTheorySet.model_validate(read_json(candidates[0]))


def load_kernel_set_from_run(ctx: RunContext) -> Stage3KernelSet:
    stage_dir = ctx.stage_dir("stage_03")
    candidates = list(stage_dir.glob("council-kernels-*.json"))
    if not candidates:
        raise FileNotFoundError(f"No Stage 3 artifact in {stage_dir}")
    return Stage3KernelSet.model_validate(read_json(candidates[0]))


def load_theory_set_from_run(ctx: RunContext) -> Stage4TheorySet:
    stage_dir = ctx.stage_dir("stage_04")
    candidates = list(stage_dir.glob("triplet-theories-*.json"))
    if not candidates:
        raise FileNotFoundError(f"No Stage 4 artifact in {stage_dir}")
    return Stage4TheorySet.model_validate(read_json(candidates[0]))


# ─────────────────────────────────────────────────────────────────────────
# Stage drivers (thin pass-throughs that keep import order flat).
# ─────────────────────────────────────────────────────────────────────────

async def drive_stage_00(
    ctx: RunContext,
    topic: str,
    *,
    non_interactive: bool = False,
) -> QuestionDossier:
    from cogtide.stages.stage_00 import run_stage_00
    return await run_stage_00(ctx, topic, non_interactive=non_interactive)


async def drive_stage_01(
    ctx: RunContext,
    dossier: QuestionDossier,
) -> Stage1IdeaSet:
    from cogtide.stages.stage_01 import run_stage_01
    return await run_stage_01(ctx, dossier)


async def run_pipeline(
    ctx: RunContext,
    dossier: QuestionDossier,
    idea_set: Stage1IdeaSet,
) -> Stage4TheorySet:
    """Run the v2 peer-prediction pipeline from Stage 2 through Stage 4.

    Assumes Stage 0 (dossier) and Stage 1 (ideas) are already complete.
    This is the main orchestrator for the v2 redesign.

    Calibration flow:
    - Load historical calibration from prior runs before Stage 2.
    - Pass calibration weights into Stage 2, 3, and 4 scoring.
    - After each stage, update calibration with outcome data.
    - After Stage 4, save updated calibration for future runs.
    """
    from cogtide.stages.stage_02 import run_stage_02
    from cogtide.stages.stage_03 import run_stage_03
    from cogtide.stages.stage_04 import run_stage_04
    from cogtide.evaluation.forecasting import build_calibration_records
    from cogtide.evaluation.calibration import (
        update_within_run_calibration,
        compute_calibration_weights,
        summarize_calibration_for_memory,
    )
    from cogtide.memory import (
        compile_run_memory,
        examine_and_compress_memory,
        save_calibration_records,
        save_calibration_aggregate,
        load_calibration_aggregate,
    )
    from cogtide.models.scorecards import ReviewerCalibrationRecord
    from cogtide.models.review_signals import TheoryPeerReviewSet

    dossier_summary = dossier.consolidated_summary
    expert_ids = idea_set.expert_ids or sorted({
        i.source_lens for i in idea_set.ideas
    })

    # ── Load historical calibration from prior runs ───────────────────
    existing_aggregate = load_calibration_aggregate()
    historical_cal = [
        ReviewerCalibrationRecord.model_validate(r) for r in existing_aggregate
    ]
    historical_weights = compute_calibration_weights(historical_cal)
    if historical_weights:
        print(f"[Pipeline] Loaded historical calibration for "
              f"{len(historical_weights)} reviewers")

    # ── Stage 2: Peer-Screened Coalition Synthesis ────────────────────
    deep_theory_set = await run_stage_02(
        ctx, idea_set, dossier_summary,
        calibration_weights=historical_weights or None,
    )

    # Within-run calibration update: idea screening predictions vs outcomes
    accepted_idea_ids = set()
    for dt in deep_theory_set.deep_theories:
        accepted_idea_ids.update(dt.contributing_idea_ids)

    peer_reviews = load_idea_peer_reviews_from_run(ctx)
    calibration_records: list[ReviewerCalibrationRecord] = []
    if peer_reviews:
        calibration_records = build_calibration_records(
            peer_reviews, accepted_idea_ids, run_id=ctx.run_id,
        )

    # Also update calibration from Stage 2 external panel reviews
    s2_dir = ctx.stage_dir("stage_02")
    accepted_dt_ids_s2 = {dt.id for dt in deep_theory_set.deep_theories}
    for panel_path in sorted(s2_dir.glob("external-panel-reviews-D*.json")):
        try:
            panel_data = read_json(panel_path)
            panel_set = TheoryPeerReviewSet.model_validate(panel_data)
            # The deep theory survived Stage 2 if it was accepted
            s2_panel_cal = build_calibration_records(
                panel_set, accepted_dt_ids_s2, run_id=ctx.run_id,
            )
            calibration_records = update_within_run_calibration(
                calibration_records, s2_panel_cal,
            )
        except Exception as e:
            print(
                f"[Pipeline] Skipping calibration update from "
                f"{panel_path.name} (non-fatal): {e}"
            )

    # Compute updated weights for Stage 3
    cal_weights = compute_calibration_weights(calibration_records)

    # ── Stage 3: Peer-Scored Council Synthesis ────────────────────────
    kernel_set = await run_stage_03(
        ctx, deep_theory_set, dossier_summary,
        calibration_weights=cal_weights or None,
    )

    # Update calibration from Stage 3 external panel reviews.
    #
    # TODO(design): Stage 2 panel reviewers also forecast whether each deep
    # theory would survive INTO Stage 3 (i.e. contribute to a kernel:
    # {dtid for k in kernel_set.kernels for dtid in k.contributing_deep_theory_ids}).
    # Scoring those forecasts against the kernel outcome here would
    # strengthen the calibration signal, but it re-weights reviewers who
    # already contributed records above, so it is left as a deliberate
    # design decision rather than silently changed.
    s3_dir = ctx.stage_dir("stage_03")
    accepted_kernel_ids = {k.id for k in kernel_set.kernels}
    for panel_path in sorted(s3_dir.glob("external-panel-reviews-K*.json")):
        try:
            panel_data = read_json(panel_path)
            panel_set = TheoryPeerReviewSet.model_validate(panel_data)
            s3_panel_cal = build_calibration_records(
                panel_set, accepted_kernel_ids, run_id=ctx.run_id,
            )
            calibration_records = update_within_run_calibration(
                calibration_records, s3_panel_cal,
            )
        except Exception as e:
            print(
                f"[Pipeline] Skipping calibration update from "
                f"{panel_path.name} (non-fatal): {e}"
            )

    # ── Stage 4: Peer-Calibrated Triplet Elaboration ─────────────────
    theory_set = await run_stage_04(
        ctx, kernel_set, dossier_summary,
        all_expert_ids=expert_ids,
    )

    # ── Post-pipeline: Compile memory and calibration ─────────────────
    cal_summary = summarize_calibration_for_memory(calibration_records)

    # Save calibration records for this run
    save_calibration_records(
        ctx.run_id,
        [r.model_dump() for r in calibration_records],
    )

    # Merge with aggregate calibration for future runs
    merged = update_within_run_calibration(historical_cal, calibration_records)
    save_calibration_aggregate([r.model_dump() for r in merged])

    # Compile run memory
    stage_artifacts = {
        "dossier": dossier.model_dump(),
        "ideas": [i.model_dump() for i in idea_set.ideas],
        "deep_theories": [dt.model_dump() for dt in deep_theory_set.deep_theories],
        "kernels": [k.model_dump() for k in kernel_set.kernels],
        "theories": [t.model_dump() for t in theory_set.theories],
    }
    try:
        await compile_run_memory(
            ctx.client,
            ctx.run_id,
            stage_artifacts,
            calibration_summary=cal_summary,
        )
    except Exception as e:
        print(f"[Pipeline] compile_run_memory failed (non-fatal): {e}")

    mem_cfg = (ctx.config or {}).get("memory", {}) or {}
    if mem_cfg.get("enabled", True):
        try:
            report = await examine_and_compress_memory(
                ctx.client,
                ctx.run_id,
                threshold_chars=mem_cfg.get("raw_threshold_chars"),
            )
            if report.compressed:
                print(
                    f"[Pipeline] Memory compressed: {report.raw_record_count} raw "
                    f"records ({report.raw_total_chars} chars) -> "
                    f"{report.snapshot_path}"
                )
            else:
                print(
                    f"[Pipeline] Memory compression skipped: {report.reason} "
                    f"({report.raw_total_chars}/{report.threshold_chars} chars)"
                )
        except Exception as e:
            print(f"[Pipeline] examine_and_compress_memory failed (non-fatal): {e}")

    return theory_set


async def run_full_pipeline(
    ctx: RunContext,
    topic: str,
    *,
    non_interactive: bool = False,
) -> Stage4TheorySet:
    """End-to-end driver: Stage 0 → 1 → 2 → 3 → 4.

    Use this when no prior run artifacts exist. The CLI's ``run`` subcommand
    calls this; the ``stage_XX`` subcommands call the individual drivers and
    ``run_pipeline`` separately so partial resume is possible.
    """
    dossier = await drive_stage_00(ctx, topic, non_interactive=non_interactive)
    idea_set = await drive_stage_01(ctx, dossier)
    return await run_pipeline(ctx, dossier, idea_set)
