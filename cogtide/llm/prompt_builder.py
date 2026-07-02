"""Prompt builder. Loads markdown prompt files and substitutes simple placeholders.

Prompts live under prompts/ as plain markdown so they are diffable and can be
edited without touching orchestration code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PROMPT_ROOT = Path(__file__).resolve().parents[2] / "prompts"

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def load_prompt(relative_path: str) -> str:
    """Load a prompt file from prompts/<relative_path>."""
    path = PROMPT_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, context: dict[str, Any]) -> str:
    """Substitute {{ key }} placeholders. Missing keys raise KeyError."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"Missing prompt context key: {key}")
        return str(context[key])

    return _PLACEHOLDER_RE.sub(repl, template)


def load_and_render(relative_path: str, context: dict[str, Any]) -> str:
    return render_prompt(load_prompt(relative_path), context)


def compose_with_shared(
    relative_path: str,
    shared: list[str],
    context: dict[str, Any],
    *,
    stage_base: str | None,
) -> str:
    """Compose a stage prompt with shared base prompts prepended.

    Layout (top to bottom):
        1. shared bases from prompts/shared/<name> (one per `shared` entry)
        2. `stage_base` loaded from prompts/<stage_base> — used when a
           stage has a single base prompt that all per-agent prompts in
           that stage delegate to (e.g. "stage_02/BASE_S02_coalition.md").
           Pass ``stage_base=None`` explicitly to opt out when a stage
           genuinely has no base file (Stage 0).
        3. the per-agent prompt at prompts/<relative_path>

    Each section is separated by `\\n\\n---\\n\\n`. Placeholders like
    `{{ key }}` are substituted using `context`.

    The ``stage_base`` parameter is **keyword-only and required** (no
    default). This is deliberate: in a prior version of this codebase
    (ttm-theory-atlas) the argument had a ``None`` default and multiple
    stages silently dropped their per-stage base prompt because
    callers forgot to pass it. Making the parameter required turns
    that failure mode into a loud ``TypeError``. If you really do want
    to compose without a stage base, pass ``stage_base=None`` explicitly.
    """
    parts = [load_prompt(f"shared/{name}") for name in shared]
    if stage_base is not None:
        parts.append(load_prompt(stage_base))
    parts.append(load_prompt(relative_path))
    return render_prompt("\n\n---\n\n".join(parts), context)
