# Counterexample: justified build after a real no-fit sweep

**Label:** real — this is deja-vu's own founding prior-art hunt, already published in `docs/design.md` §6. No simulated data.

**Verdict:** BUILD · **Confidence:** high · **Degraded lanes:** Snowball, Probe (unaddressed by any found candidate) · **Evidence gaps:** see residual uncertainty below · **Unresolved ambiguity:** none — the gap itself is the basis for the verdict

## Problem

A structured prior-art hunt needs: re-problem, a blind-parallel multi-source sweep with
snowballing, hands-on probing, context-weighted judging, an imperative gate, and a durable
record/learn loop. Four real candidate skills plus one essay were found and compared; none
covers the full nine-stage loop.

## Why this is a *justified* build, not a reflexive one

This is the case the skill exists to prevent by default — and it is also the proof the skill
applies its own discipline to itself. The comparison table in `docs/design.md` §6 scores each
candidate against all nine stages, not just "is there something similar": `trelmitt/claude-skills`
covers Trigger strongly and Judge/Record partially; the other three cover even less. The BUILD
verdict was not "nothing looked similar" — it was "the closest candidate covers roughly a third
of the stages, and the missing stages (Re-problem, Snowball, Probe, imperative Gate, Learn) are
exactly where the value is." The verdict was also human-gated, not agent-authorized, because a
multi-stage skill with its own schema and scripts is a low-reversibility commitment.

## Receipts

- `docs/design.md` §6 comparison table (all nine stages × four candidates + one essay).
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
exemplar covers why `vercel-labs/skills` was composed in as a lane rather than treated as
a whole-loop competitor here.
