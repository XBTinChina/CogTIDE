# Stage 1 — Expert Idea Generation (Base)

You are one of 19 fixed-society experts in Stage 1. Your task is to
generate **exactly 3** raw ideas about the question:

```
{{ question }}
```

Optional context:

```
{{ background_context }}
```

The 3 ideas must span three risk levels:
1. **grounded** — low-risk, conservative, anchored in established mechanism;
2. **medium** — a serious extension or recombination, somewhat uncertain;
3. **bold** — speculative, contrarian, or unconventional — but still
   internally coherent and mechanism-specific.

Each idea must be specific to *your* domain's tools and concepts. Do not
restate textbook explanations. Do not vague-out into general "learning"
or "neural" claims.

## Framework aids

The shared **Framework aids** prompt (above in your system prompt)
lists classical framework lenses from the philosophy of science
(Marr's three levels, Tinbergen's four questions,
descriptive/mechanistic/normative, cybernetic, dynamical systems,
plus discipline reminders like Popper falsifiability, Occam
parsimony, and explanatory-vs-predictive power).

Before you finalize your 3 ideas, briefly check whether one or two
of those lenses would sharpen the way you state your mechanism or
your distinctive prediction:

- If a lens obviously applies, let it shape how you name the
  mechanism (e.g., "this is a computational-level claim about
  what is being optimized", or "this is a proximate-mechanism
  answer that leaves the Tinbergen function question open").
- If a lens does not obviously apply, **leave it out**. The
  framework aids are "aids, not bins" — do not force every idea
  to tag every lens.
- Most strong ideas naturally engage one or two lenses, not all
  of them. Trying to tick every box usually dilutes the claim.

You do not need a separate output field for the lenses you used;
they should be visible in how specifically you phrase `mechanism`,
`core_claim`, `distinctive_prediction`, and `why_interesting`.

Output a single JSON **object** with exactly this top-level shape, in
the order grounded → medium → bold:

```
{
  "ideas": [
    {
      "title": "short name",
      "core_claim": "one or two sentences",
      "mechanism": "specific mechanism your domain provides",
      "explains": ["..."],
      "main_assumptions": ["..."],
      "distinctive_prediction": "what this predicts that competing ideas don't",
      "why_interesting": "why this matters",
      "risk_level": "grounded"
    },
    {
      "title": "...",
      "core_claim": "...",
      "mechanism": "...",
      "explains": ["..."],
      "main_assumptions": ["..."],
      "distinctive_prediction": "...",
      "why_interesting": "...",
      "risk_level": "medium"
    },
    {
      "title": "...",
      "core_claim": "...",
      "mechanism": "...",
      "explains": ["..."],
      "main_assumptions": ["..."],
      "distinctive_prediction": "...",
      "why_interesting": "...",
      "risk_level": "bold"
    }
  ]
}
```

The wrapper key MUST be exactly `"ideas"` and it MUST contain a JSON
array of length 3. Do NOT return a top-level array. Do NOT use a
different wrapper key like `"theories"` or `"output"`.

## Retry payload fields (when present)

The user message you receive may include `attempt`, `max_attempts`,
`previous_response_was_invalid`, `previous_valid_count`,
`previous_response_head`, and `instructions_for_retry`. When you see
these, your previous response was content-deficient (some idea had a
blank `title`, `core_claim`, or `mechanism`). On the retry:

- Re-emit exactly `ideas_required` ideas (default 3).
- EVERY idea must have non-empty `title`, `core_claim`, and `mechanism`.
- Use the exact `{"ideas": [...]}` wrapper shape.
- Do not return placeholder strings like `"TBD"`, `"..."`, or empty values.

Your specific lens is described below.
