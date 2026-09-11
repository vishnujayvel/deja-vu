# Exemplar: depend on an existing skill, honestly labeled as a manual lane

**Label:** real — grounded in this repository's own documented (not automated) Sweep lane and a live, independently re-verified external repository. No simulated data.

**Verdict:** DEPEND · **Confidence:** moderate · **Degraded lanes:** none · **Evidence gaps:** health-rubric receipts (contributor absence, activity/security cadence, Scorecard) not gathered

## Problem

deja-vu's Stage 3 (Sweep) needs a way to answer "did someone already ship this as an
installable agent skill?" Building and maintaining a bespoke skill-discovery index inside
deja-vu itself would duplicate an already-solved, actively maintained problem.

## Correction from an earlier draft of this entry

An earlier version of this receipt described `vercel-labs/skills` as "wired in" and its lane
as "one blind-parallel subprocess call" implying it runs automatically as part of
`scripts/sweep.py`. That was wrong: `scripts/sweep.py`'s `ALL_LANES` is
`["github", "registry", "grep", "scorecard"]` — skills-ecosystem is not in it.
`references/lanes.md` labels the skills-ecosystem row under a section literally titled
"Manual/subagent lanes (no script yet — dispatch as blind parallel briefs)" (line 62), and
`SKILL.md`'s Stage 3 row says an agent must "dispatch remaining lanes ... as blind parallel
subagents." This is a documented instruction for an agent to follow by hand each hunt, not
code that runs itself. The packet and this receipt now describe it that way.

## Reasoning path

1. **Framing** — the need is narrow and commodity-shaped: index lookup, not verdict logic.
2. **Sweep** — `vercel-labs/skills` (`npx skills find <query>`, per its current README) is the
   established answer; `references/lanes.md` documents it as a manual skills-ecosystem lane a
   hunting agent should run by hand.
3. **Judge** — competency test: skill discovery is not deja-vu's differentiator, so adopting
   is the right default. License (MIT) and coarse activity (not archived, recently pushed)
   were checked and are healthy. The fuller health rubric `references/judge.md` actually asks
   for — contributor-absence factor, 90-day activity/release/security cadence, commit
   concentration, OpenSSF Scorecard — was **not** gathered for this candidate, so confidence is
   recorded as moderate, not high, and star count is deliberately excluded from that judgment
   (`judge.md`: "Stars are the weakest signal and must never rank candidates").
4. **Gate** — reversible (this is a documentation recommendation, not a code dependency to
   delete), commodity plumbing → agent-authorized, no human gate required.

## Why this is good reuse, not lazy reuse

The candidate solves a *different, narrower* problem than deja-vu (skill discovery vs.
prior-art verdicts), so it is composed in as one lane rather than treated as a competing
whole-loop candidate — the same distinction the schema's `fit: composable` dimension exists
to express, instead of forcing a single exact/mismatch judgment on a partial match.

## An invocation-surface detail this correction also caught

`references/lanes.md` documents `npx skills search "<vocabulary>"`. Checking
`vercel-labs/skills`' current source (`src/cli.ts` lines 333–334) shows `find` is the
documented command and `search` is still accepted as an undocumented alias
(`case 'find': case 'search':`). The lane still works today, but a future release could drop
the alias without notice — worth fixing the documented invocation, not just noting it here.

## Receipts

- `gh api repos/vercel-labs/skills` — verified 2026-09-11: license MIT, stargazers_count
  31266, archived false, pushed_at 2026-09-08T17:31:59Z.
- `gh api repos/vercel-labs/skills/contents/README.md` and `src/cli.ts` — verified
  2026-09-11: documented command `npx skills find [query]`; `search` still works as an
  undocumented alias in source.
- `docs/design.md` §6 footnote 3 (original citation, 2026-09-04): "mature (26k+ stars)."
  Star count has grown since; not used here as a health signal either way.
- `references/lanes.md` line 62 and skills-ecosystem row; `SKILL.md` Stage 3 row.
- `scripts/sweep.py` — read directly, 2026-09-11: `ALL_LANES` does not include
  skills-ecosystem.
- Decision packet: `packet.json` in this directory (`schema_version:
  deja-vu.decision-packet/v1`, validated against `schemas/decision-packet.schema.json`).

## Distinguishing discovery from verified use

This receipt documents that deja-vu's own docs *instruct* an agent to dispatch
`vercel-labs/skills` as a manual lane (documentation-verified) and that the target repository
is real, licensed, and active (freshly re-verified via the GitHub API today). It does not
claim a hands-on run of `npx skills find` was performed while authoring this corpus entry —
evidence_level is recorded as `documented`, not `operational` or `probed`, because no such run
happened.
