# Counterexample: evidence that degraded between citation and re-verification

**Label:** real — the source-rot event described here was independently re-verified today (2026-09-11) via the GitHub API and a direct HTTP check, not assumed from the original 2026-09-04 citation. No simulated data.

**Verdict:** no route taken (recorded as a citation, not an adoption) · **Confidence:** low on the candidate's current fitness · **Degraded lanes:** Probe (never possible; now also live-source access) · **Evidence gaps:** author's reason for removing the path is unknown and unasked

## Problem

`TrevorS/dot-claude`'s `github-prior-art` skill was cited during deja-vu's founding hunt as
related prior art ("search GitHub before answering," no verdict, no scoring — `docs/design.md`
§6 footnote 2). This exemplar documents what happens to a citation's evidence quality *after*
the hunt, when the underlying source itself decays.

## What changed between citation and re-verification

- **At citation time** (2026-09-04 or earlier): the skill existed at `skills/github-prior-art`
  in the live repository; `docs/design.md` §6 already used a pinned-commit permalink rather
  than a bare `main`-branch link, anticipating exactly this risk.
- **At re-verification** (2026-09-11, this corpus entry): `gh api
  repos/TrevorS/dot-claude/contents/skills/github-prior-art` returns 404 — the path is gone
  from HEAD — while `gh api repos/TrevorS/dot-claude` shows the repository itself is still
  active (pushed 2026-09-10). Only this one path was removed. The original pinned-commit
  permalink still resolves (`curl` → HTTP 200).

## Why this is an honest "degraded evidence" example, not a fabricated one

Nothing about this candidate was ever adopted (`route: none` in the packet) — the entry exists
solely to record that evidence quality is not static. The original citation never claimed more
than a documentation-level read ("no verdict, no scoring"); it has since degraded further, from
live-browsable to pinned-permalink-only. A future re-check could find the permalink itself gone,
which the packet's `next_action` field anticipates rather than assumes won't happen.

## Receipts

- `gh api repos/TrevorS/dot-claude/contents/skills/github-prior-art` → `404 Not Found`,
  run 2026-09-11.
- `gh api repos/TrevorS/dot-claude` → `pushed_at: 2026-09-10T22:02:40Z`, `license: null`,
  run 2026-09-11.
- `curl -o /dev/null -w '%{http_code}'
  https://github.com/TrevorS/dot-claude/tree/449a215248c52106f1d13d686e4c31debe9952f5/skills/github-prior-art`
  → `200`, run 2026-09-11.
- `docs/design.md` §6 footnote 2 (original citation, already using the pinned-commit form).
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json`.
