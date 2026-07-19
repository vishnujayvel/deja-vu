# Stage 8 — Record

Two artifacts, written after the gate resolves — not before, and not skipped because the verdict
felt obvious. The record is what makes the next hunt on the same question free.

## ADR

One per decision. The "alternatives considered" section is the highest-value part 18 months from
now, when nobody remembers why the losing candidates lost.

```markdown
# ADR-<n>: <one-line decision title>

**Date:** <YYYY-MM-DD>
**Status:** accepted

## Context
<the solution-free problem from Stage 0, one paragraph>

## Options considered
| Candidate | Rubric summary | Provenance | Why it lost / won |
|---|---|---|---|
| <name> | <declared-dimension scores> | <signal> | <reason> |

## Decision
**Verdict:** <NOT-A-PROBLEM | DIFFERENT-PROBLEM | DEPEND | FORK | VENDOR | BUILD>
<one paragraph: what was adopted/built and why, referencing the fence check and
reversibility answer from Stage 6>

## Receipts
<every command run and what it returned — enough that a skeptical reader can reproduce
the verdict without re-running the whole hunt>
```

Store ADRs wherever the host project keeps its architecture docs (e.g. `docs/adr/`) — this
skill doesn't mandate a location, only that one exists per decision.

## Decisions registry

An append-only JSONL file, `data/decisions-registry.jsonl` (gitignored — it accumulates
project-specific, sometimes sensitive, history and should not ship in a public repo template).
One line per hunt:

```json
{"id": "adr-3", "date": "2026-07-19", "problem": "<solution-free statement>",
 "vocabularies": ["...", "..."], "verdict": "DEPEND", "candidate": "<name/url or null>",
 "review_by": "2027-01-19", "adr_path": "docs/adr/0003-....md"}
```

`review_by` is not optional: prior-art conclusions rot. A DEPEND verdict on a library with a
single maintainer should be re-checked sooner (3–6 months) than a VENDOR verdict on a small,
stable utility (12 months is fine). Pick the date at record time, not as an afterthought.

Stage 1 (Trigger) checks this file first, every time, before any lane runs — the `grep`/`cat`
invocation is in `SKILL.md` §0. A hunt whose registry entry hasn't hit `review_by` yet is cited,
not repeated. A stale entry gets re-validated starting at Stage 5 (Probe) on the previously
winning candidate only — not a full re-sweep from Stage 3.
