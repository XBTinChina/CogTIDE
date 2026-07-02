"""Render a Stage 3 kernel set as a human-readable markdown document.

Mirrors the role of ``stage4_markdown`` but one stage earlier: one H1
header, one H2 per accepted kernel. Each kernel surfaces the full
"core in detail" — deeper substrate, rationale, mechanism sketch, key
predictions / assumptions, preserved tensions, lineage, and the peer
scorecard — so Stage 3 output can be reviewed without a JSON viewer.
"""

from __future__ import annotations

from cogtide.models.stage3_kernel import Stage3Kernel, Stage3KernelSet


def _bulleted(items: list[str], empty: str = "_none_") -> str:
    cleaned = [str(i).strip() for i in items if i and str(i).strip()]
    if not cleaned:
        return empty
    return "\n".join(f"- {i}" for i in cleaned)


def _render_kernel(kernel: Stage3Kernel) -> str:
    underrated = "yes" if kernel.peer_is_underrated else "no"
    locally_persuasive = "yes" if kernel.peer_is_locally_persuasive_only else "no"
    lines: list[str] = [
        f"## {kernel.id} — {kernel.name}",
        "",
        "**Lineage**  ",
        (
            f"Contributing deep theories: "
            f"{', '.join(f'`{d}`' for d in kernel.contributing_deep_theory_ids) or '_none_'}  "
        ),
        (
            f"Council experts: "
            f"{', '.join(kernel.council_expert_ids) or '_none_'}  "
        ),
        (
            f"Contributing ideas: "
            f"{', '.join(f'`{i}`' for i in kernel.contributing_idea_ids) or '_none_'}  "
        ),
        (
            f"Preservation marks: "
            f"{', '.join(kernel.preserved_marks) if kernel.preserved_marks else '_none_'}"
        ),
        "",
        "**Kernel statement**",
        "",
        kernel.kernel_statement,
        "",
        "**Deeper substrate**",
        "",
        kernel.deeper_substrate,
        "",
        "**Why this is deeper than its inputs**",
        "",
        kernel.rationale,
        "",
        "**Mechanism sketch**",
        "",
        kernel.mechanism_sketch or "_not specified_",
        "",
        "**Key predictions**",
        "",
        _bulleted(kernel.key_predictions),
        "",
        "**Key assumptions**",
        "",
        _bulleted(kernel.key_assumptions),
        "",
        "**Preserved tensions**",
        "",
        kernel.preserved_tensions or "_none_",
        "",
        "**Peer scores**  ",
        (
            f"quality={kernel.peer_quality_score:.2f} · "
            f"unexpected_support={kernel.peer_unexpected_support:+.2f} · "
            f"survival_forecast={kernel.peer_survival_forecast:.2f} · "
            f"calibration_weighted={kernel.peer_calibration_weighted_score:.2f} · "
            f"disagreement={kernel.peer_reviewer_disagreement:.2f}  "
        ),
        f"_underrated:_ {underrated} · _locally persuasive only:_ {locally_persuasive}",
    ]
    if kernel.discussion_summary.strip():
        lines += ["", "**Discussion summary**", "", kernel.discussion_summary.strip()]
    if kernel.judge_notes.strip():
        lines += ["", f"_Judge notes:_ {kernel.judge_notes.strip()}"]
    return "\n".join(lines)


def render_stage3_markdown(
    result: Stage3KernelSet,
    *,
    run_id: str = "",
) -> str:
    """Render the full Stage 3 artifact as markdown."""
    header = ["# Stage 3 — Council Kernels", ""]
    if run_id:
        header.append(f"_Run:_ `{run_id}`  ")
    header += [
        f"_Accepted kernels:_ {len(result.kernels)}  ",
        f"_Target kernel count:_ {result.target_count}  ",
        f"_Total council attempts:_ {len(result.attempts)}",
        "",
        "---",
        "",
    ]
    if not result.kernels:
        return "\n".join(header + ["_No kernels accepted._", ""])
    blocks = [_render_kernel(k) for k in result.kernels]
    return "\n".join(header) + "\n\n---\n\n".join(blocks) + "\n"
