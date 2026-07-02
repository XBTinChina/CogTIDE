"""Preservation-mark survival checks across stages."""

from __future__ import annotations

from cogtide.models import Stage1IdeaSet, Stage2DeepTheorySet, Stage3KernelSet


def marked_idea_ids(idea_set: Stage1IdeaSet) -> set[str]:
    return {i.id for i in idea_set.ideas if i.preservation_marks}


def preserved_in_deep_theories(
    deep_set: Stage2DeepTheorySet, marked: set[str]
) -> tuple[set[str], set[str]]:
    """Return (preserved, missing) sets of marked idea IDs.

    A marked Stage 1 idea is "preserved" if it appears as a contributing
    idea in at least one accepted Stage 2 deep theory.
    """
    contributed: set[str] = set()
    for dt in deep_set.deep_theories:
        contributed.update(dt.contributing_idea_ids)
    preserved = marked & contributed
    missing = marked - contributed
    return preserved, missing


def preserved_in_kernels(
    kernel_set: Stage3KernelSet, marked: set[str]
) -> tuple[set[str], set[str]]:
    """Return (preserved, missing) sets of marked idea IDs.

    A marked Stage 1 idea is "preserved through Stage 3" if it appears
    in at least one accepted kernel's contributing_idea_ids.
    """
    contributed: set[str] = set()
    for k in kernel_set.kernels:
        contributed.update(k.contributing_idea_ids)
    preserved = marked & contributed
    missing = marked - contributed
    return preserved, missing
