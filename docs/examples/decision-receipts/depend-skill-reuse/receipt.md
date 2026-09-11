# Exemplar: depend on an existing skill instead of building a discovery index

**Label:** real — grounded in this repository's own shipped Sweep lane and a live, independently re-verified external repository. No simulated data.

**Verdict:** DEPEND · **Confidence:** high · **Degraded lanes:** none · **Evidence gaps:** none

## Problem

deja-vu's Stage 3 (Sweep) needs a lane that answers "did someone already ship this as an
installable agent skill?" Building and maintaining a bespoke skill-discovery index inside
deja-vu itself would duplicate an already-solved, actively maintained problem.

## Reasoning path

1. **Framing** — the need is narrow and commodity-shaped: index lookup, not verdict logic.
2. **Sweep** — `vercel-labs/skills` (`npx skills`) is the established answer; `references/lanes.md`
   already documents it as the skills-ecosystem lane.
3. **Judge** — competency test: skill discovery is not deja-vu's differentiator. License
   (MIT) and health (31k+★, active, org-backed) both clear the bar. Fence check: the tool's
   CLI surface is the load-bearing accident to track — a breaking CLI change would need to be
   caught, not silently ignored.
4. **Gate** — reversible (delete one CI-adjacent subprocess call), commodity plumbing →
   agent-authorized, no human gate required.

## Why this is good reuse, not lazy reuse

The candidate solves a *different, narrower* problem than deja-vu (skill discovery vs.
prior-art verdicts), so it was composed in as one lane rather than treated as a competing
whole-loop candidate — the same distinction the schema's `fit: composable` dimension exists
to express, instead of forcing a single exact/mismatch judgment on a partial match.

## Receipts

- `gh api repos/vercel-labs/skills` — verified 2026-09-11: license MIT, stargazers_count
  31266, archived false, pushed_at 2026-09-08T17:31:59Z.
- `docs/design.md` §6 footnote 3 (original citation, 2026-09-04): "mature (26k+ stars)."
  Star count has grown since; direction and conclusion unchanged.
- `references/lanes.md` skills-ecosystem row: `npx skills search "<vocabulary>"`.
- Decision packet: `packet.json` in this directory (`schema_version:
  deja-vu.decision-packet/v1`, validated against `schemas/decision-packet.schema.json`).

## Distinguishing discovery from verified use

This receipt documents that deja-vu's own Sweep stage *specifies* invoking `vercel-labs/skills`
as a lane (documentation-verified, via `references/lanes.md`) and that the target repository is
real, licensed, and active (freshly re-verified via the GitHub API today). It does not claim a
fresh hands-on run of `npx skills search` was performed as part of authoring this corpus entry —
that would be a claim about actual execution this entry does not make.
