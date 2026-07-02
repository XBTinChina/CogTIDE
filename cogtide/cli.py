"""CLI entry point for cogTIDE.

cogTIDE — Cognitive Theory Ideation, Debate, and Epistemic Evaluation.

Subcommands:
  stage_00 --topic "..."         Interactive clarification → QuestionDossier
  stage_01 --resume <run_id>     19-expert ideation + challenger
  stage_02 --resume <run_id>     Peer-screened coalition synthesis
  stage_03 --resume <run_id>     Peer-scored council synthesis
  stage_04 --resume <run_id>     Peer-calibrated triplet elaboration
  run      --topic "..."         Full pipeline Stage 0 → Stage 4

The per-stage commands assume all prior stages' canonical artifacts
already exist under ``runs/<run_id>/``. ``run`` drives the whole pipeline
from scratch.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from cogtide.pipeline.controller import (
    drive_stage_00,
    drive_stage_01,
    load_deep_theory_set_from_run,
    load_dossier_from_run,
    load_idea_set_from_run,
    load_kernel_set_from_run,
    run_full_pipeline,
    run_pipeline,
)
from cogtide.pipeline.run_context import RunContext


def _configure_windows_stdio() -> None:
    """Force UTF-8 on stdout/stderr on Windows to tolerate Greek/math symbols.

    Silent no-op on non-Windows.
    """
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


async def _cmd_stage_00(args: argparse.Namespace) -> int:
    ctx = RunContext.create(args.topic)
    print(f"[run_id] {ctx.run_id}")
    await drive_stage_00(ctx, args.topic, non_interactive=args.non_interactive)
    print(f"[Stage 0] Complete. Resume with:")
    print(f"  python -m cogtide.cli stage_01 --resume {ctx.run_id}")
    return 0


async def _cmd_stage_01(args: argparse.Namespace) -> int:
    ctx = RunContext.resume(args.resume)
    dossier = load_dossier_from_run(ctx)
    await drive_stage_01(ctx, dossier)
    print(f"[Stage 1] Complete. Resume with:")
    print(f"  python -m cogtide.cli stage_02 --resume {ctx.run_id}")
    return 0


async def _cmd_stage_02(args: argparse.Namespace) -> int:
    from cogtide.stages.stage_02 import run_stage_02

    ctx = RunContext.resume(args.resume)
    dossier = load_dossier_from_run(ctx)
    idea_set = load_idea_set_from_run(ctx)
    await run_stage_02(ctx, idea_set, dossier.consolidated_summary)
    print(f"[Stage 2] Complete. Resume with:")
    print(f"  python -m cogtide.cli stage_03 --resume {ctx.run_id}")
    return 0


async def _cmd_stage_03(args: argparse.Namespace) -> int:
    from cogtide.stages.stage_03 import run_stage_03

    ctx = RunContext.resume(args.resume)
    dossier = load_dossier_from_run(ctx)
    deep_theory_set = load_deep_theory_set_from_run(ctx)
    await run_stage_03(ctx, deep_theory_set, dossier.consolidated_summary)
    print(f"[Stage 3] Complete. Resume with:")
    print(f"  python -m cogtide.cli stage_04 --resume {ctx.run_id}")
    return 0


async def _cmd_stage_04(args: argparse.Namespace) -> int:
    from cogtide.stages.stage_04 import run_stage_04

    ctx = RunContext.resume(args.resume)
    dossier = load_dossier_from_run(ctx)
    idea_set = load_idea_set_from_run(ctx)
    kernel_set = load_kernel_set_from_run(ctx)
    expert_ids = idea_set.expert_ids or sorted({
        i.source_lens for i in idea_set.ideas
    })
    await run_stage_04(
        ctx, kernel_set, dossier.consolidated_summary,
        all_expert_ids=expert_ids,
    )
    print(f"[Stage 4] Complete. Run complete: {ctx.run_id}")
    return 0


async def _cmd_run(args: argparse.Namespace) -> int:
    ctx = RunContext.create(args.topic)
    print(f"[run_id] {ctx.run_id}")
    theory_set = await run_full_pipeline(
        ctx, args.topic, non_interactive=args.non_interactive,
    )
    print(f"[Pipeline] Complete: {len(theory_set.theories)} final theories")
    return 0


async def _cmd_resume_pipeline(args: argparse.Namespace) -> int:
    """Resume a run that has Stage 0 + 1 artifacts already, finishing 2-4."""
    ctx = RunContext.resume(args.resume)
    dossier = load_dossier_from_run(ctx)
    idea_set = load_idea_set_from_run(ctx)
    theory_set = await run_pipeline(ctx, dossier, idea_set)
    print(f"[Pipeline] Complete: {len(theory_set.theories)} final theories")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cogtide",
        description=(
            "cogTIDE — Cognitive Theory Ideation, Debate, and Epistemic "
            "Evaluation: a peer-calibrated, auditable LLM pipeline for "
            "theory generation."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p00 = sub.add_parser("stage_00", help="Interactive Stage 0 clarification")
    p00.add_argument("--topic", required=True, help="Raw research question")
    p00.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip user confirmation gate (CI / tests only)",
    )
    p00.set_defaults(func=_cmd_stage_00)

    p01 = sub.add_parser("stage_01", help="Run 19-expert ideation + challenger")
    p01.add_argument("--resume", required=True, help="Existing run_id")
    p01.set_defaults(func=_cmd_stage_01)

    p02 = sub.add_parser("stage_02", help="Run peer-screened coalition synthesis")
    p02.add_argument("--resume", required=True, help="Existing run_id")
    p02.set_defaults(func=_cmd_stage_02)

    p03 = sub.add_parser("stage_03", help="Run peer-scored council synthesis")
    p03.add_argument("--resume", required=True, help="Existing run_id")
    p03.set_defaults(func=_cmd_stage_03)

    p04 = sub.add_parser("stage_04", help="Run peer-calibrated triplet elaboration")
    p04.add_argument("--resume", required=True, help="Existing run_id")
    p04.set_defaults(func=_cmd_stage_04)

    pr = sub.add_parser("run", help="Full pipeline (Stage 0 → 4)")
    pr.add_argument("--topic", required=True, help="Raw research question")
    pr.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip Stage 0 confirmation gate",
    )
    pr.set_defaults(func=_cmd_run)

    prp = sub.add_parser(
        "resume_pipeline",
        help="Resume Stage 2→4 on an existing run_id (must have Stage 0+1)",
    )
    prp.add_argument("--resume", required=True, help="Existing run_id")
    prp.set_defaults(func=_cmd_resume_pipeline)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_windows_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
