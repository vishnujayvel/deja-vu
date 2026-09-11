# Counterexample: justified build after a real no-fit sweep

**Label:** real — this is deja-vu's own founding prior-art hunt, already published in `docs/design.md` §6. No simulated data.

**Verdict:** BUILD · **Confidence:** moderate · **Degraded lanes:** none (see note below on why Snowball/Probe are not "degraded lanes") · **Evidence gaps:** see residual uncertainty · **Unresolved ambiguity:** whether a human independently confirmed approval cannot be verified from this proposed-stage packet alone

## Corrections from an earlier draft of this entry

Three fixes from independent review:

1. **Stage count.** `docs/design.md` defines a **ten**-stage loop, numbered 0–9 (0 Re-problem
   through 9 Learn — see the table in §3 and the comparison table in §6). An earlier draft of
   this entry said "nine-stage" throughout and its own residual-uncertainty field said "five of
   nine" while only listing four stages, silently dropping Re-problem. Both are fixed: it's
   ten stages, and the five with no full-coverage candidate are 0, 4, 5, 7, and 9 (see below).
2. **"Degraded lanes" mislabel.** An earlier draft called Snowball and Probe "degraded lanes."
   They aren't — a "lane" in this project's vocabulary is a Stage-3 Sweep information-gathering
   source (GitHub, registry, curation, ...) that can report `degraded`/`unsupported`/`skipped`
   per `docs/design.md` §5.2's fixed vocabulary. Snowball and Probe are pipeline *stages* the
   candidates don't implement, not lanes that failed to gather evidence. This is now stated
   correctly.
3. **Approval attribution.** An earlier draft asserted the BUILD verdict "required human
   gating" as an independently established fact. This corpus has no authority receipt (every
   packet stays `stage: proposed`), so it cannot independently prove a human approved anything
   — it can only cite that `docs/design.md` §6 *reports* a human approval. That distinction is
   now explicit in the packet's `uncertainty` field.

## Problem

A structured prior-art hunt needs: re-problem, a blind-parallel multi-source sweep with
snowballing, hands-on probing, context-weighted judging, an imperative gate, and a durable
record/learn loop. Four real candidate skills plus one essay were found and compared against
all ten stages; none covers the full loop.

## Why this is a *justified* build, not a reflexive one

This is the case the skill exists to prevent by default — and it is also the proof the skill
applies its own discipline to itself. The comparison table in `docs/design.md` §6 scores each
candidate against all ten stages, not just "is there something similar": `trelmitt/claude-skills`
covers Trigger strongly and Record fully, with partial credit on Framing/Sweep/Judge; the other
three candidates cover less. Recounted precisely from the table: **five of ten stages have no
candidate scoring full coverage** — Snowball, Probe, and Learn get no mark at all from any of
the four scored candidates; Re-problem and Gate-as-imperative get at best a partial or unclear
mark from one candidate (`runx`), never a full one. The verdict was not "nothing looked
similar" — it was "the closest candidates cover roughly a third to a half of the stages, and
five stages have essentially no real prior art to build on at all."

## Receipts

- `docs/design.md` §6 comparison table (ten stages × four candidates + one essay) and §3's
  ten-stage table (0 Re-problem through 9 Learn).
- `gh api repos/trelmitt/claude-skills` re-verified 2026-09-11: license null (no LICENSE
  file), pushed_at 2026-07-10T19:34:54Z.
- `gh api repos/TrevorS/dot-claude/contents/skills/github-prior-art` re-verified 2026-09-11:
  404 — path removed from the live repository since original citation (see the companion
  `degraded-evidence-source-rot` exemplar for the full story).
- `gh api repos/vercel-labs/skills` re-verified 2026-09-11: MIT, 31266★, active.
- `gh api repos/runxhq/runx` re-verified 2026-09-11: Apache-2.0, 84★, active, path
  `skills/prior-art/SKILL.md` still present at HEAD.
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json`.

## Companion exemplars

The `rights-constrained-clean-room` exemplar isolates the licensing dimension of the
`trelmitt/claude-skills` comparison from this same real hunt; the `depend-skill-reuse`
exemplar covers why `vercel-labs/skills` was adopted as a manual lane rather than treated as
a whole-loop competitor here.
