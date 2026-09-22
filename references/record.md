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

## Revalidating a stale decision

`review_by` passing doesn't mean the prior verdict was wrong — it means the evidence is old
enough to recheck before citing it again. `SKILL.md` §0 already decides *whether* re-checking
means a targeted probe of the old winner or a fresh hunt from Stage 0; this section shows what
the resulting record looks like in both cases. Both start from the same read: the prior ADR
plus the registry line it produced. This is a manual write-up, the same as any other ADR — no
scheduler, controller, or automatic change-detector triggers it.

### Case A — framing still holds, winner re-confirmed

Framing hasn't shifted (same problem, same constraints, same exclusion criteria), so Stage 0
sends the hunt straight to Stage 5 to re-probe only the previously-winning candidate. No new
sweep, no new snowball.

```markdown
## Revalidation — ADR-3 (2027-01-22)

**Prior record:** ADR-3 (2026-07-19), registry id `adr-3`, verdict DEPEND on `foo-ratelimit`.
**Trigger:** `review_by` 2027-01-19 passed.
**Re-checked:** license unchanged (MIT), maintained (3 releases since the prior probe),
  Scorecard 7.8 (was 7.1) — no regression, no new CVEs. Framing unchanged: problem,
  constraints, and exclusion criteria match the 2026-07-19 record verbatim.
**Recommendation:** retained — DEPEND on `foo-ratelimit`.
**Unresolved uncertainty:** none new; the original probe's single-maintainer risk (noted in
  ADR-3) still stands and is not re-litigated here.
**Why a targeted probe, not a fresh hunt:** the problem statement and constraints didn't
  change — only time did. A full sweep would re-derive the same shortlist at far higher cost
  for no new information.
```

Append a new registry line — the original is never edited:

```json
{"id": "adr-3-revalidated-2027-01", "date": "2027-01-22", "problem": "<same as adr-3>",
 "vocabularies": ["..."], "verdict": "DEPEND", "candidate": "foo-ratelimit",
 "review_by": "2027-07-22", "adr_path": "docs/adr/0003-....md",
 "supersedes": "adr-3", "delta": "winner re-confirmed, no framing change"}
```

### Case B — requirements changed, treat as a new hunt

The re-check surfaces a changed constraint (a new compliance requirement, a rights change, a
license change on the incumbent) — Stage 0 routes back through Stage 0 (Re-problem) and Stage 2
(Framing), not Stage 5. The prior record isn't "wrong"; it answered a question that no longer
matches the one being asked now.

```markdown
## Revalidation — ADR-7 (2027-02-03)

**Prior record:** ADR-7 (2026-06-01), registry id `adr-7`, verdict VENDOR (reimplemented the
  idea instead of depending on the original, unlicensed prototype).
**Trigger:** `review_by` 2026-12-01 passed; the re-check also surfaced a changed requirement —
  the consuming service now needs audit logging that the original problem statement never
  scoped.
**Re-checked:** the original candidate is still unlicensed and unmaintained (last commit
  2025-08) — moot either way, since the requirement itself changed.
**Recommendation:** changed — problem restated and a fresh hunt run from Stage 0. The new hunt
  (ADR-9) found a maintained, Apache-2.0 candidate with built-in audit logging; verdict DEPEND.
**Unresolved uncertainty:** none carried forward — ADR-9's own Judge stage records its own
  gaps.
**Why a fresh hunt, not a targeted probe:** the exclusion criteria from ADR-7's framing no
  longer match what's being asked (audit logging is now in scope); re-probing the old winner
  under the old criteria would answer a question nobody is asking anymore.
```

The new hunt's own registry line (`adr-9`) records `"supersedes": "adr-7"`; ADR-7's original
line is left untouched.

### What to preserve either way

- The original ADR and registry line are never edited or deleted — append-only holds for
  revalidations too. A superseding line points backward (`supersedes`); the reverse link is
  never written into the original.
- If a source used in the original probe is unavailable at revalidation time (dead link,
  private repo, deleted account), say so explicitly in the revalidation record instead of
  silently dropping the citation — an unreachable receipt is a recorded uncertainty, not an
  omission.
- `scripts/sanitize_check.sh` applies to revalidation records the same as any other
  documentation — no machine-specific paths, emails, or secrets in the ADR or the registry
  line.
