"""Render Stage 4 theory triplets as human-readable markdown.

Two renderers live here:

* ``render_stage4_kernel_markdown`` produces one self-contained
  document per kernel. The document leads with a plain-language
  background, an analogy, and per-variant plain summaries, then
  follows with the full technical detail. The audience is a curious
  non-specialist; the technical detail is preserved so a specialist
  can still verify the work.
* ``render_stage4_markdown`` produces the aggregate run-level index.
  When per-kernel docs exist it links to them; when they do not it
  falls back to the original concatenated layout so the index file
  stays useful on its own.
"""

from __future__ import annotations

from typing import Any, Sequence

from cogtide.models.stage3_kernel import Stage3Kernel
from cogtide.models.stage4_theory import (
    Stage4Theory,
    Stage4TheorySet,
    Stage4Triplet,
)


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def _bulleted(items: list[str], empty: str = "_none_") -> str:
    cleaned = [str(i).strip() for i in items if i and str(i).strip()]
    if not cleaned:
        return empty
    return "\n".join(f"- {i}" for i in cleaned)


def _paragraph(text: str, empty: str = "_not specified_") -> str:
    t = (text or "").strip()
    return t if t else empty


def _maybe_section(title: str, body: str) -> list[str]:
    """Emit a section only when body is non-empty. Returned lines are
    ready to ``"\n".join`` into the document."""
    body = (body or "").strip()
    if not body:
        return []
    return [f"## {title}", "", body, ""]


def _glossary_block(entries: Sequence[dict[str, str]]) -> str:
    cleaned: list[str] = []
    for entry in entries:
        term = str(entry.get("term", "")).strip()
        plain = str(entry.get("plain", "")).strip()
        if term and plain:
            cleaned.append(f"- **{term}** — {plain}")
    if not cleaned:
        return ""
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Per-kernel document
# ---------------------------------------------------------------------------

ROLE_TAGLINES: dict[str, str] = {
    "core": "the most balanced version — what you would publish today",
    "solid": "the most defensible version — narrower scope, fewer risks",
    "risky": "the boldest version — highest upside if it turns out right",
}


def _render_variant_accessible(
    theory: Stage4Theory,
    explainer_role: dict[str, Any],
) -> str:
    """One variant block: plain-language framing first, technical detail
    after, with peer scores at the end."""
    role_label = theory.role.upper()
    tagline = ROLE_TAGLINES.get(theory.role, "")

    plain_summary = (explainer_role.get("plain_summary") or "").strip()
    plain_analogy = (explainer_role.get("plain_analogy") or "").strip()
    why_this_role = (explainer_role.get("why_this_role") or "").strip()
    glossary = _glossary_block(explainer_role.get("glossary", []) or [])

    lines: list[str] = [
        f"## {role_label} variant — {theory.name}  `{theory.id}`",
        "",
    ]
    if tagline:
        lines += [f"_{tagline}._", ""]

    if plain_summary:
        lines += ["### In plain English", "", plain_summary, ""]
    if plain_analogy:
        lines += ["**Analogy.** " + plain_analogy, ""]
    if why_this_role:
        lines += [
            f"**Why this is the {theory.role} variant.** " + why_this_role,
            "",
        ]
    if glossary:
        lines += [
            "**Key terms used below**",
            "",
            glossary,
            "",
        ]

    lines += [
        "### Technical detail",
        "",
        f"**Central claim.** {theory.central_claim}",
        "",
        "**Statement**",
        "",
        _paragraph(theory.statement),
        "",
        "**Ontology** — the variables and entities the theory talks about",
        "",
        _bulleted(theory.ontology),
        "",
        "**Mechanism** — how the variables interact step by step",
        "",
        _paragraph(theory.mechanism),
        "",
    ]

    lines.append("**Formal sketch** — equations / pseudocode / formal model")
    lines.append("")
    if theory.formal_sketch.strip():
        lines += ["```", theory.formal_sketch.strip(), "```", ""]
    else:
        lines += ["_not specified_", ""]

    lines += [
        "**Boundary conditions** — when the theory is meant to apply",
        "",
        _bulleted(theory.boundary_conditions),
        "",
        "**Main assumptions**",
        "",
        _bulleted(theory.main_assumptions),
        "",
        "**Distinctive predictions** — what this variant says that rivals don't",
        "",
        _bulleted(theory.distinctive_predictions),
        "",
        "**Testable predictions** — operational predictions you could check",
        "",
        _bulleted(theory.testable_predictions),
        "",
        "**Falsifiers** — observations that would clearly break the theory",
        "",
        _bulleted(theory.falsifiers),
        "",
        "**Measurement strategy** — how to actually measure the key variables",
        "",
        _bulleted(theory.measurement_strategy),
        "",
        "**Phenomena explained**",
        "",
        _bulleted(theory.phenomena_explained),
        "",
        "**Open questions**",
        "",
        _bulleted(theory.open_questions),
        "",
        "### Peer scores",
        "",
        (
            f"coherence={theory.peer_coherence:.2f} · "
            f"defensibility={theory.peer_defensibility:.2f} · "
            f"novelty={theory.peer_novelty:.2f} · "
            f"distinctiveness={theory.peer_distinctiveness:.2f} · "
            f"experimental_fertility={theory.peer_experimental_fertility:.2f} · "
            f"upside_if_true={theory.peer_upside_if_true:.2f} · "
            f"**balanced={theory.peer_balanced_score:.2f}**"
        ),
        "",
        f"_Role confirmed by external panel:_ "
        f"{'yes' if theory.role_confirmed_by_peers else 'no'}",
    ]
    if theory.notes:
        lines += ["", f"_Notes:_ {theory.notes}"]
    return "\n".join(lines)


def _render_kernel_technical_block(kernel: Stage3Kernel) -> str:
    lines: list[str] = [
        "## The technical kernel",
        "",
        f"**Kernel statement.** {kernel.kernel_statement}",
        "",
    ]
    if kernel.deeper_substrate.strip():
        lines += [
            "**Deeper substrate** — the shared architecture the council found",
            "",
            kernel.deeper_substrate.strip(),
            "",
        ]
    if kernel.rationale.strip():
        lines += [
            "**Rationale** — why this kernel is deeper than its inputs",
            "",
            kernel.rationale.strip(),
            "",
        ]
    if kernel.mechanism_sketch.strip():
        lines += [
            "**Mechanism sketch**",
            "",
            kernel.mechanism_sketch.strip(),
            "",
        ]
    if kernel.key_predictions:
        lines += [
            "**Key predictions**",
            "",
            _bulleted(kernel.key_predictions),
            "",
        ]
    if kernel.key_assumptions:
        lines += [
            "**Key assumptions**",
            "",
            _bulleted(kernel.key_assumptions),
            "",
        ]
    if kernel.preserved_tensions.strip():
        lines += [
            "**Preserved tensions** — disagreements the council kept rather than papered over",
            "",
            kernel.preserved_tensions.strip(),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def render_stage4_kernel_markdown(
    *,
    triplet: Stage4Triplet,
    kernel: Stage3Kernel,
    explainer: dict[str, Any] | None = None,
    run_id: str = "",
) -> str:
    """Render one kernel and its three theories as a single, accessible
    markdown document.

    The document opens with a plain-language background and analogy
    (when the explainer provided them), gives a quick reading guide
    to the core / solid / risky variants, then follows with the full
    technical detail of the kernel and each variant. Peer scores and
    panel metadata sit at the end so they don't crowd the reading
    path but are still on hand for review.
    """
    explainer = explainer or {}
    bg = (explainer.get("kernel_background") or "").strip()
    analogy = (explainer.get("kernel_analogy") or "").strip()
    overview = (explainer.get("triplet_overview") or "").strip()

    lines: list[str] = [
        f"# {kernel.id} — {kernel.name}",
        "",
    ]
    meta_bits: list[str] = []
    if run_id:
        meta_bits.append(f"_Run:_ `{run_id}`")
    meta_bits.append(f"_Parent kernel:_ `{kernel.id}`")
    meta_bits.append(
        f"_Theories in this triplet:_ "
        f"`{triplet.core_theory.id}` (core), "
        f"`{triplet.solid_theory.id}` (solid), "
        f"`{triplet.risky_theory.id}` (risky)"
    )
    lines.append("  \n".join(meta_bits))
    lines.append("")

    # Plain-language opening — only emitted when the explainer
    # actually populated content, so a failed explainer pass leaves
    # the document looking deliberate rather than half-finished.
    if bg or analogy or overview:
        lines += ["## What this kernel is about", ""]
        if bg:
            lines += [bg, ""]
        if analogy:
            lines += [
                "### A way to picture it",
                "",
                analogy,
                "",
            ]
        if overview:
            lines += [
                "### Why three theories, not one",
                "",
                overview,
                "",
            ]

    lines.append(_render_kernel_technical_block(kernel))
    lines.append("")

    lines += [
        "## The three theories at a glance",
        "",
        f"- **CORE — {triplet.core_theory.name}** (`{triplet.core_theory.id}`): "
        f"the most balanced version. Strong on all dimensions.",
        f"- **SOLID — {triplet.solid_theory.name}** (`{triplet.solid_theory.id}`): "
        f"the most defensible version. Narrower scope, fewer risks.",
        f"- **RISKY — {triplet.risky_theory.name}** (`{triplet.risky_theory.id}`): "
        f"the boldest version. Highest upside if right.",
        "",
    ]

    explainer_roles = {
        "core": explainer.get("core") or {},
        "solid": explainer.get("solid") or {},
        "risky": explainer.get("risky") or {},
    }

    for theory in (
        triplet.core_theory,
        triplet.solid_theory,
        triplet.risky_theory,
    ):
        lines.append(_render_variant_accessible(theory, explainer_roles[theory.role]))
        lines.append("")

    # Provenance / panel metadata sits at the end.
    lines += ["## How this triplet was built", ""]
    panel_str = ", ".join(triplet.panel_expert_ids) if triplet.panel_expert_ids else "_none_"
    lines += [f"- **Local panel experts:** {panel_str}"]
    lines += [f"- **Revision rounds used:** {triplet.revision_rounds_used}"]
    if triplet.peer_review_panel_ids:
        lines += [
            "- **External peer panel:** "
            + ", ".join(triplet.peer_review_panel_ids),
        ]
    lines += [
        f"- **Roles reassigned by external peers:** "
        f"{'yes' if triplet.roles_reassigned else 'no'}",
    ]
    if triplet.roles_reassigned and triplet.reassignment_rationale:
        lines += ["", f"> {triplet.reassignment_rationale}", ""]

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Aggregate index document
# ---------------------------------------------------------------------------

def _render_theory_compact(theory: Stage4Theory) -> str:
    """Compact technical view used by the aggregate index when
    per-kernel files are not available."""
    role_confirmed = "yes" if theory.role_confirmed_by_peers else "no"
    lines: list[str] = [
        f"### {theory.id} — {theory.role.upper()} — {theory.name}",
        "",
        f"**Parent kernel:** `{theory.parent_kernel}`  ",
        f"**Role confirmed by peers:** {role_confirmed}",
        "",
        f"**Central claim.** {theory.central_claim}",
        "",
        "**Statement**",
        "",
        _paragraph(theory.statement),
        "",
        "**Ontology**",
        "",
        _bulleted(theory.ontology),
        "",
        "**Mechanism**",
        "",
        _paragraph(theory.mechanism),
        "",
        "**Formal sketch**",
        "",
    ]
    if theory.formal_sketch.strip():
        lines += ["```", theory.formal_sketch.strip(), "```"]
    else:
        lines.append("_not specified_")
    lines += [
        "",
        "**Boundary conditions**",
        "",
        _bulleted(theory.boundary_conditions),
        "",
        "**Main assumptions**",
        "",
        _bulleted(theory.main_assumptions),
        "",
        "**Distinctive predictions**",
        "",
        _bulleted(theory.distinctive_predictions),
        "",
        "**Testable predictions**",
        "",
        _bulleted(theory.testable_predictions),
        "",
        "**Falsifiers**",
        "",
        _bulleted(theory.falsifiers),
        "",
        "**Measurement strategy**",
        "",
        _bulleted(theory.measurement_strategy),
        "",
        "**Phenomena explained**",
        "",
        _bulleted(theory.phenomena_explained),
        "",
        "**Open questions**",
        "",
        _bulleted(theory.open_questions),
        "",
        "**Peer scores**  ",
        (
            f"coherence={theory.peer_coherence:.2f} · "
            f"defensibility={theory.peer_defensibility:.2f} · "
            f"novelty={theory.peer_novelty:.2f} · "
            f"distinctiveness={theory.peer_distinctiveness:.2f} · "
            f"experimental_fertility={theory.peer_experimental_fertility:.2f} · "
            f"upside_if_true={theory.peer_upside_if_true:.2f} · "
            f"**balanced={theory.peer_balanced_score:.2f}**"
        ),
    ]
    if theory.notes:
        lines += ["", f"_Notes:_ {theory.notes}"]
    return "\n".join(lines)


def _render_triplet_compact(triplet: Stage4Triplet) -> str:
    reassigned = "yes" if triplet.roles_reassigned else "no"
    header = [
        f"## Triplet for `{triplet.parent_kernel}`",
        "",
        f"**Panel experts:** "
        f"{', '.join(triplet.panel_expert_ids) if triplet.panel_expert_ids else '_none_'}  ",
        f"**Revision rounds used:** {triplet.revision_rounds_used}  ",
        f"**Roles reassigned by peers:** {reassigned}",
    ]
    if triplet.roles_reassigned and triplet.reassignment_rationale:
        header += ["", f"> {triplet.reassignment_rationale}"]
    blocks = ["\n".join(header)]
    for t in (triplet.core_theory, triplet.solid_theory, triplet.risky_theory):
        blocks.append(_render_theory_compact(t))
    return "\n\n".join(blocks)


def render_stage4_markdown(
    result: Stage4TheorySet,
    *,
    run_id: str = "",
    kernel_doc_links: Sequence[tuple[str, str, str]] | None = None,
) -> str:
    """Render the run-level Stage 4 index.

    When ``kernel_doc_links`` is supplied (one ``(kernel_id, kernel_name,
    filename)`` triple per kernel), the index becomes a slim navigation
    page: a per-kernel table of contents plus a peer-score summary row
    for each triplet. When it is empty (e.g. older callers), the index
    falls back to the original concatenated layout so the file stays
    self-sufficient.
    """
    header = ["# Stage 4 — Theory Triplets", ""]
    if run_id:
        header.append(f"_Run:_ `{run_id}`  ")
    header += [
        f"_Total triplets:_ {len(result.triplets)}  ",
        f"_Total theories:_ {len(result.theories)}",
        "",
    ]
    if not result.triplets:
        return "\n".join(header + ["_No triplets produced._", ""])

    # If we have per-kernel docs, the aggregate file is a thin index:
    # readers click through to a kernel doc to get the actual content.
    if kernel_doc_links:
        link_index = {kid: (kname, fname) for (kid, kname, fname) in kernel_doc_links}
        header += [
            "Each kernel has its own self-contained markdown file with the",
            "plain-language background, analogy, and full technical detail",
            "for its three theories. The summary table below links to them.",
            "",
            "## Per-kernel documents",
            "",
            "| Kernel | Name | Document |",
            "| --- | --- | --- |",
        ]
        for triplet in result.triplets:
            kid = triplet.parent_kernel
            kname, fname = link_index.get(kid, (kid, ""))
            link = f"[{fname}]({fname})" if fname else "_(missing)_"
            header.append(f"| `{kid}` | {kname} | {link} |")
        header.append("")
        header += [
            "## Triplet peer-score summary",
            "",
            "| Kernel | Variant | Theory | Balanced | Coherence | Defensibility | Novelty |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for triplet in result.triplets:
            for theory in (
                triplet.core_theory,
                triplet.solid_theory,
                triplet.risky_theory,
            ):
                header.append(
                    f"| `{triplet.parent_kernel}` "
                    f"| {theory.role} "
                    f"| `{theory.id}` {theory.name} "
                    f"| {theory.peer_balanced_score:.2f} "
                    f"| {theory.peer_coherence:.2f} "
                    f"| {theory.peer_defensibility:.2f} "
                    f"| {theory.peer_novelty:.2f} |"
                )
        header.append("")
        return "\n".join(header)

    # Fallback path: full content inline (preserves prior behaviour).
    triplet_blocks = [_render_triplet_compact(t) for t in result.triplets]
    return (
        "\n".join(header) + "---\n\n" + "\n\n---\n\n".join(triplet_blocks) + "\n"
    )
