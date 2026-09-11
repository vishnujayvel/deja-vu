# Exemplar: depend on a host CLI/runtime capability instead of a custom detector

**Label:** real — grounded in this repository's own `evals/run_evals.py` source and Claude Code's official public documentation. No simulated data.

**Verdict:** DEPEND (with an honest degrade path) · **Confidence:** moderate · **Degraded lanes:** none · **Evidence gaps:** no live run performed; detection functions have no test coverage in this repository

## Correction from an earlier draft of this entry

An earlier version of this receipt (and this directory's original name,
`depend-model-capability/`) called this a "model capability." That was inaccurate:
`--output-format stream-json` is a **Claude Code CLI/runtime feature** — documented at
`https://code.claude.com/docs/en/cli-usage` — not a capability of the underlying language
model itself. The directory was renamed to `depend-cli-runtime-capability/` and the wording
below corrected accordingly. It also previously claimed `evidence_level: operational` and
"Evidence gaps: none"; neither was true — this corpus entry read source and official docs, it
never ran a live headless session. Both are corrected below.

## Problem

`evals/run_evals.py --live` needs to detect, per trigger-case prompt, whether the deja-vu
skill actually fired inside a headless Claude Code session — without deja-vu building and
maintaining a bespoke log-scraping or reply-text-classification harness.

## Reasoning path

1. **Framing** — the need is "did a specific skill tool_use event occur," which a structured
   event stream can answer directly, versus inferring intent from prose.
2. **Sweep** — Claude Code's `--output-format stream-json` flag on `claude -p` emits that
   structured event stream (confirmed against the official docs, not just this repo's own
   description of it). `evals/run_evals.py` parses it via `skill_invoked_in_stream()` /
   `_event_has_deja_vu_skill()` (lines 354–414), looking for a `Skill`/`skill` tool_use event
   whose serialized payload mentions "deja-vu."
3. **Judge** — fit is strong but not universal: `claude_supports_stream_json()` (lines
   341–351) probes `claude --help` for the substring `"stream-json"` **once**, before any
   trigger cases run, and that single check picks the whole run's `detection_mode`
   (`"stream-json"` or `"text-grep"`, lines 455–456) — a runtime failure partway through a
   stream-json run does **not** trigger a fallback; only the upfront `--help` check does. An
   earlier draft implied the fallback reacts to runtime failures, which the code does not do.
4. **Gate** — reversible, commodity capability → agent-authorized.

## Why this is a host capability, not a general tool

Unlike the `depend-skill-reuse` exemplar (a third-party CLI package), this feature ships with
the agent host runtime itself. The lesson still generalizes: before building a custom
output-parsing/classification layer around an LLM agent host, check whether the host already
emits a structured signal for the exact event you're trying to detect — just don't call that
signal a "model capability" when it's actually a runtime/CLI one; the distinction matters for
where you'd go to report a bug or track a breaking change (the CLI's release notes, not a
model-card changelog).

## Honest limits

- No live headless run was performed while authoring this corpus entry — the claim rests on
  reading `evals/run_evals.py`'s source and the official CLI docs, which is `evidence_level:
  source-inspected`, not `operational` or `probed`.
- `grep -rn "skill_invoked_in_stream\|detect_fired\|claude_supports_stream_json" tests/`
  returns no matches (checked 2026-09-11) — these detection functions have no dedicated test
  coverage in this repository.
- `--live` is explicitly experimental and excluded from CI (per the module docstring itself).
- The event schema is an external, unversioned surface Claude Code controls, not deja-vu —
  an upstream change could silently break detection.

## Receipts

- `https://code.claude.com/docs/en/cli-usage` — `--output-format` flag, `stream-json` value,
  verified 2026-09-11.
- `evals/run_evals.py` lines 341–426 (`claude_supports_stream_json`,
  `skill_invoked_in_stream`, `_event_has_deja_vu_skill`, `detect_fired`) and lines 455–456
  (detection-mode selection) — read directly from this repository's tracked source, 2026-09-11.
- `grep -rn "skill_invoked_in_stream\|detect_fired\|claude_supports_stream_json" tests/` — no
  matches, 2026-09-11.
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json`.
