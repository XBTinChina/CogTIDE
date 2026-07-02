"""Stage 0: Question Clarification.

Interactive loop that drives the clarifier agent until it produces a
QuestionDossier and the user confirms it. Writes the canonical
artifact ``stage_00/question-<run_id>.json`` (and ``.md``).

Context injection
-----------------
Before the first clarifier call, Stage 0 searches the top-level
``question/`` directory for **subfolders** whose names are relevant to
the user's question (simple token-overlap scoring). If one candidate
subfolder is found, the user is asked ``y/n``; if multiple, the user
picks one. The ``overview.md`` file at the top of ``question/`` is
deliberately **not** read — context comes from whichever topic
subfolder the user confirms. All ``.md`` / ``.txt`` / ``.rst`` files in
that subfolder are concatenated (up to a total character budget) and
handed to the clarifier as ``overview_text``.

Long / multi-line user input
----------------------------
macOS tty canonical mode caps a single ``input()`` line at ~1024 bytes
and splits pasted text at embedded newlines, which causes long-paragraph
pastes to freeze or be silently truncated. To work around this, the
clarification and dossier-feedback prompts accept three commands:

- ``:edit`` — opens ``$EDITOR`` (or ``nano``) on a temp file; saving
  + quitting returns the file's contents as the answer.
- ``:file <path>`` — reads the answer from the file at ``<path>``
  (``~`` is expanded).
- ``:multi`` — switches to multi-line entry; end with ``:end`` on
  its own line.

Plain single-line input continues to work for short answers, ``y/yes``,
and ``q/quit/exit``.

Clarifier contract (three-layer defense)
----------------------------------------
1. Prompt rule: the clarifier must return
   ``{"status": "needs_more_input", ...}`` on ``call_index == 1``.
2. Stage-logic rule: if the LLM returns a dossier on ``call_index == 1``,
   we reject it and re-ask.
3. CLI rule: after a draft dossier is emitted, the user must type
   ``y`` (or ``yes``) to accept. Anything else is appended as refinement
   feedback and the loop continues. A hard ceiling
   ``stages.stage_00.max_clarification_rounds`` caps total LLM turns.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from cogtide.llm.prompt_builder import compose_with_shared
from cogtide.memory import extract_keywords, retrieve_for_consumer
from cogtide.models import QuestionDossier
from cogtide.pipeline.run_context import RunContext
from cogtide.utils.ids import slugify, timestamp_now
from cogtide.utils.io import write_json, write_text

SHARED_BASES = [
    "BASE_reasoning.md",
    "BASE_json_contract.md",
    "BASE_output_contract.md",
    "BASE_traceability.md",
]

CLARIFIER_PROMPT_PATH = "stage_00/AG_S00_SS04_question_clarifier.md"
DEFAULT_MAX_ROUNDS = 5
QUESTION_ROOT = Path(__file__).resolve().parents[2] / "question"

# Text extensions we will ingest from a confirmed subfolder. Binary files
# and other extensions are skipped.
_TEXT_EXTS = {".md", ".txt", ".rst", ".markdown"}

# Names we will never ingest even if they match the text-extension set.
_IGNORED_FILENAMES = {"overview.md", "README.md", "readme.md", ".DS_Store"}

# Hard ceiling on total ingested context characters (per folder).
_MAX_CONTEXT_CHARS = 500_000

# Simple English stopword set for question/folder-name tokenization.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "into", "are",
    "was", "were", "how", "why", "what", "which", "when", "where", "who",
    "whom", "whose", "does", "did", "can", "could", "would", "should",
    "must", "may", "might", "have", "has", "had", "but", "not", "nor",
    "you", "your", "yours", "they", "their", "them", "our", "its",
    "about", "there", "here", "over", "under", "out", "off", "any",
    "some", "all", "most", "more", "less", "than", "then", "such",
})

# ---------------------------------------------------------------------------
# Subfolder discovery + context ingestion
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Lowercase, alphanumeric tokens ≥3 chars, minus stopwords."""
    tokens = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _list_candidate_subfolders(question_root: Path) -> list[Path]:
    """Return direct subdirectories of ``question/`` ignoring dot-dirs."""
    if not question_root.exists() or not question_root.is_dir():
        return []
    return sorted(
        p for p in question_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def score_subfolders_against_topic(
    topic: str,
    folders: Iterable[Path],
) -> list[tuple[Path, int]]:
    """Return ``[(folder, score)]`` sorted by score desc for nonzero scores.

    Score = number of tokens in the folder name that also appear in the
    question. This is deliberately simple so the user can quickly audit
    why a folder was picked.
    """
    topic_tokens = _tokenize(topic)
    scored: list[tuple[Path, int]] = []
    for f in folders:
        folder_tokens = _tokenize(f.name)
        overlap = len(topic_tokens & folder_tokens)
        if overlap:
            scored.append((f, overlap))
    scored.sort(key=lambda x: (-x[1], x[0].name))
    return scored


def read_context_from_folder(
    folder: Path,
    *,
    max_total_chars: int = _MAX_CONTEXT_CHARS,
) -> str:
    """Concatenate every text file under ``folder`` (recursive)."""
    if not folder.exists() or not folder.is_dir():
        return ""

    chunks: list[str] = []
    total = 0
    files = sorted(
        p for p in folder.rglob("*")
        if p.is_file()
        and p.suffix.lower() in _TEXT_EXTS
        and p.name not in _IGNORED_FILENAMES
    )
    for path in files:
        try:
            body = path.read_text(encoding="utf-8-sig")
        except Exception as e:
            print(f"[Stage 0] skipping {path.name}: {e}")
            continue
        rel = path.relative_to(folder).as_posix()
        header = f"\n\n--- {rel} ---\n"
        remaining = max_total_chars - total - len(header)
        if remaining <= 0:
            print(
                f"[Stage 0] context budget reached at {total} chars; "
                f"skipping remaining files"
            )
            break
        chunk = header + body[:remaining]
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks)


def _select_subfolder_interactively(
    matches: list[tuple[Path, int]],
) -> Path | None:
    """Ask the user to confirm / pick one of the matched subfolders."""
    if not matches:
        return None

    if len(matches) == 1:
        folder, score = matches[0]
        print(
            f"\n[Stage 0] Found one context subfolder matching the question:"
        )
        print(f"  - {folder.name}  (token overlap {score})")
        reply = _prompt_user(
            "Use this folder's files as background? [y/N]: "
        ).strip().lower()
        return folder if reply in {"y", "yes"} else None

    print(f"\n[Stage 0] Found {len(matches)} candidate context subfolders:")
    for i, (folder, score) in enumerate(matches, 1):
        print(f"  {i}. {folder.name}  (token overlap {score})")
    print(f"  0. (skip — use no subfolder context)")
    reply = _prompt_user(
        f"Pick one [0-{len(matches)}]: "
    ).strip()
    if not reply or reply == "0":
        return None
    try:
        idx = int(reply)
    except ValueError:
        print("[Stage 0] invalid selection; skipping context.")
        return None
    if 1 <= idx <= len(matches):
        return matches[idx - 1][0]
    print("[Stage 0] selection out of range; skipping context.")
    return None


def select_and_ingest_context(
    topic: str,
    *,
    question_root: Path | None = None,
    non_interactive: bool = False,
) -> tuple[str, str]:
    """Locate a subfolder relevant to ``topic`` and return its concatenated
    text context plus a short note naming the source.

    Returns ``(context_text, context_file_note)``. Both strings are empty
    if no folder was selected.
    """
    root = question_root or QUESTION_ROOT
    folders = _list_candidate_subfolders(root)
    if not folders:
        return "", ""

    matches = score_subfolders_against_topic(topic, folders)
    if not matches:
        print(
            f"[Stage 0] No subfolders in {root.name}/ matched the question "
            f"by name; running without folder context."
        )
        return "", ""

    if non_interactive:
        selected = matches[0][0]
        print(
            f"[Stage 0] non-interactive: auto-selected subfolder "
            f"'{selected.name}' (score {matches[0][1]})"
        )
    else:
        selected = _select_subfolder_interactively(matches)

    if selected is None:
        return "", ""

    text = read_context_from_folder(selected)
    if not text:
        print(f"[Stage 0] subfolder '{selected.name}' had no readable files.")
        return "", f"Selected context folder '{selected.name}' (empty)"
    print(
        f"[Stage 0] ingested {len(text)} chars from "
        f"{selected.relative_to(root)}"
    )
    return text, f"Context folder: question/{selected.relative_to(root)}"


# ---------------------------------------------------------------------------
# Dossier rendering + shape checks
# ---------------------------------------------------------------------------


def _is_dossier_shape(parsed: dict[str, Any]) -> bool:
    """True if parsed looks like a dossier (has core dossier fields)."""
    if not isinstance(parsed, dict):
        return False
    if parsed.get("status") == "needs_more_input":
        return False
    return all(
        isinstance(parsed.get(k), str) and parsed.get(k)
        for k in ("clarified_question", "core_question", "consolidated_summary")
    )


def render_dossier_markdown(d: QuestionDossier) -> str:
    """Pretty-print a dossier for the confirmation gate + on-disk audit."""
    lines: list[str] = []
    lines.append(f"# Question Dossier\n")
    lines.append(f"**Original question:** {d.original_question}\n")
    lines.append(f"**Clarified question:** {d.clarified_question}\n")
    lines.append(f"**Core question:** {d.core_question}\n")
    lines.append(f"**Target phenomenon:** {d.target_phenomenon}\n")
    lines.append(f"**Why it matters:** {d.why_it_matters}\n")
    lines.append(f"**Scope:** {d.scope}\n")
    if d.constraints:
        lines.append("**Constraints:**\n")
        for c in d.constraints:
            lines.append(f"- {c}")
        lines.append("")
    if d.background_context:
        lines.append(f"**Background context:** {d.background_context}\n")
    if d.relevant_distinctions:
        lines.append("**Relevant distinctions:**\n")
        for x in d.relevant_distinctions:
            lines.append(f"- {x}")
        lines.append("")
    if d.known_assumptions:
        lines.append("**Known assumptions:**\n")
        for x in d.known_assumptions:
            lines.append(f"- {x}")
        lines.append("")
    if d.remaining_open_points:
        lines.append("**Remaining open points:**\n")
        for x in d.remaining_open_points:
            lines.append(f"- {x}")
        lines.append("")
    if d.context_file_note:
        lines.append(f"**Context file note:** {d.context_file_note}\n")
    lines.append(f"**Consolidated summary:** {d.consolidated_summary}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Clarifier interaction
# ---------------------------------------------------------------------------


async def _clarification_call(
    ctx: RunContext,
    *,
    original_question: str,
    overview_text: str,
    memory_context: str,
    transcript: list[dict[str, str]],
    open_points: list[str],
    call_index: int,
    user_signaled_finalize: bool,
) -> tuple[dict[str, Any], str]:
    """Single clarifier LLM call. Returns (parsed_json, raw_text)."""
    system_prompt = compose_with_shared(
        CLARIFIER_PROMPT_PATH,
        SHARED_BASES,
        {},
        stage_base=None,
    )

    payload = {
        "original_question": original_question,
        "overview_text": overview_text,
        "memory_context": memory_context,
        "transcript_so_far": transcript,
        "open_points": open_points,
        "call_index": call_index,
        "user_signaled_finalize": user_signaled_finalize,
    }
    user_message = json.dumps(payload, ensure_ascii=False)

    parsed, record = await ctx.client.chat_json(
        agent_id=f"S00_clarifier_call{call_index}",
        system_prompt=system_prompt,
        user_message=user_message,
        expect="object",
    )

    if not record.succeeded:
        raise RuntimeError(
            f"Stage 0 clarifier call {call_index} failed: {record.last_error}"
        )

    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Stage 0 clarifier call {call_index} returned non-object "
            f"(type={type(parsed).__name__}); raw head="
            f"{record.raw_response[:200]!r}"
        )

    return parsed, record.raw_response


def _read_multiline_until_sentinel(sentinel: str = ":end") -> str:
    """Read lines from stdin until ``sentinel`` appears alone on a line.

    Used as a workaround for the macOS tty canonical-mode 1024-byte buffer
    limit. Each line still goes through ``input()``, so any single line
    must still be under 1024 bytes — but the user can paste paragraph by
    paragraph (or use ``:edit`` / ``:file`` for one-shot large pastes).
    """
    print(f"[multi-line input mode — end with '{sentinel}' on its own line]")
    lines: list[str] = []
    while True:
        try:
            ln = input()
        except EOFError:
            break
        if ln.strip() == sentinel:
            break
        lines.append(ln)
    return "\n".join(lines)


def _read_from_file(path: str) -> str:
    """Load an answer from a text file (``~`` is expanded). Returns ''
    and prints a notice on error so the loop can re-prompt.
    """
    p = Path(path).expanduser()
    try:
        text = p.read_text(encoding="utf-8")
        print(f"[Stage 0] loaded {len(text)} chars from {p}")
        return text
    except Exception as e:
        print(f"[Stage 0] could not read {path}: {e}")
        return ""


def _read_from_editor() -> str:
    """Open ``$EDITOR`` (or ``nano``) on a temp file and return its contents.

    This bypasses the tty input path entirely, so arbitrarily long answers
    (including embedded newlines and characters that confuse the terminal)
    can be entered without any buffer-limit issues.
    """
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="-stage0-answer.txt", delete=False, encoding="utf-8",
    ) as f:
        tmp_path = Path(f.name)
        f.write(
            "# Write your answer below. Lines beginning with '#' are ignored.\n"
            "# Save and quit your editor when done.\n"
        )
    try:
        try:
            subprocess.run([editor, str(tmp_path)], check=False)
        except FileNotFoundError:
            print(
                f"[Stage 0] editor '{editor}' not found; "
                f"set $EDITOR or install nano."
            )
            return ""
        raw = tmp_path.read_text(encoding="utf-8")
        # Strip the helper-comment lines we wrote into the template.
        kept = [ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")]
        answer = "\n".join(kept).strip()
        print(f"[Stage 0] editor returned {len(answer)} chars")
        return answer
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


def _prompt_user(prompt: str) -> str:
    """Get a line of input from the user, with long-input escape hatches.

    Returns the first line typed by the user UNLESS it is one of the
    command-prefix forms below, in which case the appropriate alternative
    input flow runs and its result is returned:

    - ``:multi``     — read multiple lines until ``:end`` on its own line.
    - ``:edit``      — open ``$EDITOR`` (or ``nano``) for free-form entry.
    - ``:file PATH`` — read the answer from ``PATH`` (``~`` expanded).

    Plain text input is unchanged, so ``y/yes/q/quit`` and short answers
    work exactly as before. The escape hatches exist because macOS's tty
    canonical mode caps a single line at ~1024 bytes and splits pasted
    text at embedded newlines, which causes long-paragraph pastes to
    appear to freeze or be silently truncated.
    """
    try:
        line = input(prompt)
    except EOFError:
        return ""

    cmd = line.strip()
    if cmd == ":multi":
        return _read_multiline_until_sentinel()
    if cmd == ":edit":
        return _read_from_editor()
    if cmd.startswith(":file "):
        return _read_from_file(cmd[len(":file "):].strip())
    if cmd == ":file":
        print("[Stage 0] usage: ':file <path>' (the path is required).")
        return ""
    return line


async def run_stage_00(
    ctx: RunContext,
    topic: str,
    *,
    overview_text: str | None = None,
    context_file_note: str = "",
    non_interactive: bool = False,
) -> QuestionDossier:
    """Drive the clarifier to completion and write the canonical artifact.

    If ``overview_text`` is None, Stage 0 scans ``question/`` for matching
    subfolders, asks the user to confirm / pick one, and concatenates all
    text files in the selected folder. The top-level ``overview.md`` is
    intentionally excluded.

    If ``non_interactive`` is True, the function auto-selects the
    highest-scoring subfolder (if any), runs a single clarifier round of
    questions, and finalizes on the next call with
    ``user_signaled_finalize=True``. Intended for CI / tests; real use
    should run via the CLI where the user reviews the dossier.
    """
    stage_cfg = ctx.config.get("stages", {}).get("stage_00", {})
    max_rounds = int(stage_cfg.get("max_clarification_rounds", DEFAULT_MAX_ROUNDS))

    if overview_text is None:
        overview_text, note = select_and_ingest_context(
            topic, non_interactive=non_interactive,
        )
        if note and not context_file_note:
            context_file_note = note

    memory_result = retrieve_for_consumer(
        ctx.config,
        stage="stage_00",
        consumer="clarifier",
        question_keywords=extract_keywords(topic, overview_text[:4000]),
    )
    memory_context = memory_result.rendered_context or ""
    if memory_context:
        print(
            f"[Stage 0] Injected prior-run memory "
            f"({len(memory_result.selected_raw_memories)} raw, "
            f"{len(memory_result.selected_topic_memories)} topic)"
        )

    transcript: list[dict[str, str]] = []
    open_points: list[str] = []
    call_index = 0
    dossier: QuestionDossier | None = None

    while dossier is None:
        call_index += 1
        if call_index > max_rounds + 2:
            raise RuntimeError(
                f"Stage 0 exceeded {max_rounds} clarification rounds "
                f"(plus refinement turns). Aborting."
            )

        user_signaled_finalize = (
            non_interactive or call_index > max_rounds
        )

        parsed, raw_text = await _clarification_call(
            ctx,
            original_question=topic,
            overview_text=overview_text,
            memory_context=memory_context,
            transcript=transcript,
            open_points=open_points,
            call_index=call_index,
            user_signaled_finalize=user_signaled_finalize,
        )

        # Enforce "first call must ask questions" in stage logic too.
        if call_index == 1 and _is_dossier_shape(parsed):
            print(
                "[Stage 0] Clarifier tried to finalize on call 1; rejecting "
                "and requesting questions."
            )
            transcript.append({
                "role": "system",
                "content": (
                    "Your previous response tried to finalize the dossier on "
                    "call 1. This is forbidden. Respond with "
                    '{"status": "needs_more_input", "questions_for_user": [...]}.'
                ),
            })
            continue

        # Branch on response shape.
        if parsed.get("status") == "needs_more_input":
            questions = parsed.get("questions_for_user") or []
            if not isinstance(questions, list):
                questions = [str(questions)]
            print(f"\n[Stage 0] Clarifier (round {call_index}) asks:")
            for i, q in enumerate(questions, 1):
                print(f"  {i}. {q}")

            if non_interactive:
                transcript.append({"role": "clarifier", "content": json.dumps(parsed)})
                transcript.append({
                    "role": "user",
                    "content": "(no additional input provided; please finalize)",
                })
                continue

            answer = _prompt_user(
                "\nType your answers — for long paragraphs use ':edit' "
                "(opens editor),\n':file <path>' (load from file), or "
                "':multi' (multi-line, end with ':end').\n"
                "Blank line = finalize; 'q' = abort.\n> "
            ).strip()
            if answer.lower() in {"q", "quit", "exit"}:
                raise RuntimeError("Stage 0 aborted by user.")
            transcript.append({"role": "clarifier", "content": json.dumps(parsed)})
            transcript.append({
                "role": "user",
                "content": answer if answer else "(blank — please finalize)",
            })
            open_points = parsed.get("open_points", open_points)
            continue

        if not _is_dossier_shape(parsed):
            print(
                f"[Stage 0] Response was neither 'needs_more_input' nor a "
                f"dossier. Raw head: {raw_text[:200]!r}"
            )
            transcript.append({
                "role": "system",
                "content": (
                    "Your previous response was neither a questions block nor "
                    "a complete dossier. Please return either "
                    '{"status": "needs_more_input", ...} or a dossier with '
                    "clarified_question, core_question, consolidated_summary, "
                    "and the other required fields."
                ),
            })
            continue

        # Build and show the draft dossier.
        parsed.setdefault("original_question", topic)
        parsed.setdefault("constraints", [])
        parsed.setdefault("background_context", "")
        parsed.setdefault("relevant_distinctions", [])
        parsed.setdefault("known_assumptions", [])
        parsed.setdefault("context_file_note", context_file_note)
        parsed.setdefault("remaining_open_points", [])
        parsed.setdefault("why_it_matters", "")
        parsed.setdefault("target_phenomenon", parsed.get("core_question", ""))
        parsed.setdefault("scope", "")
        # If the LLM omitted context_file_note but we selected a folder,
        # respect our note.
        if context_file_note and not parsed.get("context_file_note"):
            parsed["context_file_note"] = context_file_note

        try:
            draft = QuestionDossier.from_normalized(parsed)
        except Exception as e:
            print(f"[Stage 0] Dossier failed Pydantic validation: {e}")
            transcript.append({
                "role": "system",
                "content": (
                    f"Your draft dossier failed validation: {e}. Please "
                    "re-emit a full dossier with all required fields."
                ),
            })
            continue

        print("\n" + "=" * 68)
        print(render_dossier_markdown(draft))
        print("=" * 68)

        if non_interactive:
            dossier = draft
            break

        reply = _prompt_user(
            "\nAccept this dossier? 'y' = accept, 'q' = abort, "
            "anything else = refinement feedback.\n"
            "(For long feedback use ':edit', ':file <path>', or ':multi'.)\n> "
        ).strip()
        if reply.lower() in {"y", "yes"}:
            dossier = draft
            break
        if reply.lower() in {"q", "quit", "exit"}:
            raise RuntimeError("Stage 0 aborted by user.")
        transcript.append({"role": "clarifier", "content": json.dumps(parsed)})
        transcript.append({
            "role": "user",
            "content": (
                "I have feedback on the draft dossier. Please incorporate "
                f"the following: {reply}"
            ),
        })

    # Persist canonical artifact.
    stage_dir = ctx.stage_dir("stage_00")
    topic_slug = slugify(topic)
    ts = timestamp_now()
    json_path = stage_dir / f"question-{topic_slug}-{ts}.json"
    md_path = stage_dir / f"question-{topic_slug}-{ts}.md"
    write_json(json_path, dossier.model_dump())
    write_text(md_path, render_dossier_markdown(dossier))
    print(f"[Stage 0] Wrote dossier to {json_path}")

    return dossier
