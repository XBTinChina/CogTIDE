"""Chunking and compact-formatting helpers.

Used by:
- Stage 1 challenger: chunk 19*3 = 57 ideas into batches of 10 to avoid 504s
- Stage 2 focus batches: 57 ideas partitioned into 12 per-distiller batches
- Stage 3 debate: per-agent feedback bundles instead of one global bundle
"""

from __future__ import annotations

import random
from typing import Iterable, TypeVar

T = TypeVar("T")


def chunk_list(items: list[T], size: int) -> list[list[T]]:
    """Split a list into chunks of at most `size` items."""
    if size <= 0:
        return [list(items)]
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_focus_batches(
    items: list[T], n_batches: int, *, seed: int
) -> list[list[T]]:
    """Seeded shuffle + round-robin into n_batches groups.

    Deterministic for a given (items, n_batches, seed). Used by Stage 2
    to assign sanitized packets to distiller focus batches such that:
      (a) every item lands in exactly one batch,
      (b) the seeded shuffle breaks any correlation between input order
          and upstream grouping (e.g. Stage 1 expert identity), and
      (c) batch sizes differ by at most 1.

    With 57 items and 12 batches, the output is a list of 12 lists:
    nine of size 5 and three of size 4. Raising n_batches > len(items)
    produces some empty batches, which is allowed.
    """
    rng = random.Random(seed)
    shuffled = list(items)
    rng.shuffle(shuffled)
    batches: list[list[T]] = [[] for _ in range(n_batches)]
    for i, item in enumerate(shuffled):
        batches[i % n_batches].append(item)
    return batches


def format_idea_compact(idea: dict) -> str:
    """Compact 2-line idea format for batch challenger contexts."""
    return (
        f"[{idea.get('id', '?')}] {idea.get('title', 'Untitled')} "
        f"(risk: {idea.get('risk_level', '?')})\n"
        f"  Core claim: {idea.get('core_claim', '')[:200]}"
    )


def format_ideas_compact(ideas: Iterable[dict]) -> str:
    """Format ideas as a compact list (~2 lines each)."""
    return "\n".join(format_idea_compact(i) for i in ideas)


def format_unit_compact(unit: dict) -> str:
    """Compact format for Stage 2 units."""
    return (
        f"[{unit.get('id', '?')}] {unit.get('name', 'Unnamed')}\n"
        f"  Explanatory core: {unit.get('explanatory_core', '')[:240]}"
    )


def format_units_compact(units: Iterable[dict]) -> str:
    return "\n".join(format_unit_compact(u) for u in units)


def format_kernel_summary(kernel: dict) -> str:
    """One-paragraph kernel summary used by Stage 3 sequential differentiation."""
    name = kernel.get("name", "Unnamed kernel")
    kid = kernel.get("id", "?")
    paragraphs = kernel.get("central_explanatory_core", [])
    if isinstance(paragraphs, list) and paragraphs:
        first = paragraphs[0]
    elif isinstance(paragraphs, str):
        first = paragraphs.split("\n\n")[0]
    else:
        first = ""
    return f"[{kid}] {name}: {first[:400]}"


def format_kernels_summaries(kernels: Iterable[dict]) -> str:
    return "\n\n".join(format_kernel_summary(k) for k in kernels)


def format_scorecard_compact(scorecard: dict) -> str:
    """Compact one-line scorecard summary for inline context."""
    q = scorecard.get("quality_score", 0)
    us = scorecard.get("unexpected_support", 0)
    sf = scorecard.get("survival_forecast", 0)
    ur = scorecard.get("is_underrated", False)
    tag = " [UNDERRATED]" if ur else ""
    return f"Q={q:.1f} US={us:+.1f} SF={sf:.2f}{tag}"


def format_idea_with_scorecard(idea: dict, scorecard: dict | None = None) -> str:
    """Compact idea format with peer scorecard appended."""
    base = format_idea_compact(idea)
    if scorecard:
        base += f" | {format_scorecard_compact(scorecard)}"
    return base


def format_deep_theory_compact(dt: dict) -> str:
    """Compact format for a Stage 2 deep theory with peer scores."""
    did = dt.get("id", "?")
    name = dt.get("name", "Unnamed")
    q = dt.get("peer_quality_score", 0)
    us = dt.get("peer_unexpected_support", 0)
    return (
        f"[{did}] {name} (Q={q:.1f} US={us:+.1f})\n"
        f"  Statement: {dt.get('statement', '')[:200]}"
    )
