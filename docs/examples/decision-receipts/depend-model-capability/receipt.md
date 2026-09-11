# Exemplar: depend on a platform capability instead of a custom detector

**Label:** real — grounded in this repository's own `evals/run_evals.py` module docstring. No simulated data.

**Verdict:** DEPEND (with an honest degrade path) · **Confidence:** moderate · **Degraded lanes:** none · **Evidence gaps:** none

## Problem

`evals/run_evals.py --live` needs to detect, per trigger-case prompt, whether the deja-vu
skill actually fired inside a headless Claude Code session — without deja-vu building and
maintaining a bespoke log-scraping or reply-text-classification harness.

## Reasoning path

1. **Framing** — the need is "did a specific skill tool_use event occur," which is exactly
   what a structured event stream answers directly, versus inferring intent from prose.
2. **Sweep** — Claude Code's own `--output-format stream-json --verbose` flag on `claude -p`
   emits that structured event stream. This is a platform/model capability, not a third-party
   library — the closest prior-art kind the schema offers is `service`.
3. **Judge** — fit is strong but not universal: older Claude Code versions or hosts that only
   return final text don't support `stream-json`. Rather than treat that as a blocker, the
   design keeps a weaker fallback (grep the reply text for "deja-vu") so detection degrades
   gracefully instead of failing hard.
4. **Gate** — reversible, commodity capability → agent-authorized.

## Why this is "existing model capability," not "existing tool"

Unlike the `depend-skill-reuse` exemplar (a third-party CLI), this capability ships with the
runtime itself. The lesson generalizes: before building a custom output-parsing/classification
layer around an LLM or agent host, check whether the host already emits a structured signal for
the exact event you're trying to detect.

## Honest limits

- `--live` is explicitly experimental and excluded from CI (per the module docstring itself).
- The event schema is an external, unversioned surface Claude Code controls, not deja-vu —
  an upstream change could silently break detection. This residual uncertainty is carried in
  the decision packet rather than smoothed over.

## Receipts

- `evals/run_evals.py` module docstring (`--live` mode section), read directly from this
  repository's tracked source, 2026-09-11.
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json`.
