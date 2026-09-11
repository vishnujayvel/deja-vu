# Counterexample: evidence that changed between citation and re-verification

**Label:** real — the source-path removal described here was independently re-verified today (2026-09-11) via the GitHub API and a direct HTTP check, not assumed from the original 2026-09-04 citation. No simulated data.

**Verdict:** no route taken (recorded as a citation, not an adoption) · **Confidence:** low on the candidate's current fitness against the live repository · **Degraded lanes:** not applicable — no route was ever taken · **Evidence gaps:** cause/scope of the removal unknown; pinned-snapshot probe not attempted

## Corrections from an earlier draft of this entry

Independent review caught two overclaims:

1. **"Only this one path was removed."** A 404 on one path plus a recently-pushed repository
   does not prove nothing else changed. The packet now states only what was checked: this
   specific path is absent at HEAD; the broader scope and cause of the removal are unknown.
2. **"A hands-on probe is no longer possible."** That conflated the live HEAD (where the path
   really is gone) with the pinned-commit snapshot (which still resolves at HTTP 200 and
   remains clonable/checkoutable at that exact commit). A probe of the frozen snapshot was
   never actually attempted by this corpus entry — it's not that one is impossible, it's that
   this entry didn't do it. The packet's `evidence_level` stays `documented`, and the gap is
   now named precisely rather than described as a blanket impossibility.

## Problem

`TrevorS/dot-claude`'s `github-prior-art` skill was cited during deja-vu's founding hunt as
related prior art ("search GitHub before answering," no verdict, no scoring — `docs/design.md`
§6 footnote 2). This exemplar documents what happens to a citation's evidence quality *after*
the hunt, when the underlying source changes — precisely, not by inference.

## What was actually checked (2026-09-11)

- `gh api repos/TrevorS/dot-claude/contents/skills/github-prior-art` → `404 Not Found`. This
  path is gone from HEAD.
- `gh api repos/TrevorS/dot-claude` → `pushed_at: 2026-09-10T22:02:40Z`, `license: null`. The
  repository is active and unlicensed. This does **not** establish that only the cited path
  changed — no diff of the repository's history was run.
- `curl -o /dev/null -w '%{http_code}' https://github.com/TrevorS/dot-claude/tree/449a215248c52106f1d13d686e4c31debe9952f5/skills/github-prior-art`
  → `200`. The pinned-commit permalink `docs/design.md` §6 already used resolves, and would
  support a clone/checkout at that commit if a probe were performed — which this entry did not
  do.

## Why this is an honest "degraded evidence" example

Nothing about this candidate was ever adopted (`route: none` in the packet) — the entry exists
solely to record that evidence changes over time, and to say exactly what is and isn't known
rather than rounding uncertainty up to a stronger or weaker claim than what was checked. The
original citation never claimed more than a documentation-level read ("no verdict, no
scoring"); what changed since is narrowly scoped to "this path is gone from live HEAD," not
"everything about this candidate is now unknowable."

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
