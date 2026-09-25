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
**Confidence:** <Judge's confidence note from Stage 6, e.g. "high" or "moderate — see evidence gaps below">
**Degraded lanes:** <comma-separated lane names that reported `degraded`/`unsupported`/`skipped`, or `none`>
**Evidence gaps:** <what coverage is still missing and why, or `none`>
**Unresolved ambiguity:** <any Stage 6 disagreement or open question the verdict doesn't resolve, or `none`>
**Sources:** <the winning candidate's provenance identifiers — repo/package/URL, or `none` for
NOT-A-PROBLEM/BUILD — exactly what goes in the registry line's `sources` below>
**Review by:** <YYYY-MM-DD — the same date recorded in the registry line's `review_by`>
<one paragraph: what was adopted/built and why, referencing the fence check and
reversibility answer from Stage 6>

## Receipts
<every command run and what it returned — enough that a skeptical reader can reproduce
the verdict without re-running the whole hunt>
```

Store ADRs wherever the host project keeps its architecture docs (e.g. `docs/adr/`) — this
skill doesn't mandate a location, only that one exists per decision.

**Privacy boundary:** an ADR is a tracked, public project artifact — it ships in the repo
alongside everything else. The registry is not (see gitignore check below). Keep the ADR's
Context, Options table, and Decision paragraph free of anything that's sensitive only because
it's project-local: internal service or repo names, unreleased-feature codenames, credentials-
adjacent detail, or a level of candidate detail the project wouldn't otherwise publish. If a
fence check or provenance note genuinely needs that detail to make sense, put it in the
registry's `problem` or `sources` fields instead and keep the ADR's own language generic
enough to publish as written.

## Decisions registry

An append-only JSONL file, `data/decisions-registry.jsonl` (gitignored — it accumulates
project-specific, sometimes sensitive, history and should not ship in a public repo template).

Before the first create-or-append in a host project, verify the protection instead of assuming
it: run `git ls-files --error-unmatch data/decisions-registry.jsonl` (exit `0` means the file is
already tracked; exit `1` means it isn't) and `git check-ignore data/decisions-registry.jsonl`
(exit `0` means it's ignored; exit `1` means it isn't). Both must exit `1`/`0` respectively —
untracked and ignored — before an append. If `check-ignore` exits `1` and no `.gitignore` rule
for it exists, add the exact line `/data/decisions-registry.jsonl` to the host project's root
`.gitignore` and re-run `check-ignore` to confirm it now matches. If `ls-files --error-unmatch`
exits `0` (the file is already tracked — removing it from tracking is a host-project decision
this skill doesn't make unilaterally) or protection still can't be confirmed, don't append —
pick a user-approved external location instead, or stop and hand off to the human. No script or
framework needed, just the two git commands above; once protection is confirmed, appends stay
append-only as described below. One line per hunt:

```json
{"id": "adr-3", "date": "2026-07-19", "problem": "<solution-free statement>",
 "vocabularies": ["...", "..."], "verdict": "DEPEND", "candidate": "example-org/example-lib",
 "sources": ["gh:example-org/example-lib"],
 "confidence": "high", "degraded_lanes": [], "evidence_gaps": [], "unresolved_ambiguity": [],
 "review_by": "2027-01-19", "adr_path": "docs/adr/0003-....md"}
```

`sources` is the same provenance identifiers as the ADR Decision block's `**Sources:**` line
above — not the full "Options considered" table, just the winning candidate's repo/package/URL
— so a reader deciding whether a cited hunt still applies doesn't have to open the ADR to see
where the confidence came from. Empty array `[]` for NOT-A-PROBLEM/BUILD, matching the ADR's
`none`.

`confidence`, `degraded_lanes`, `evidence_gaps`, and `unresolved_ambiguity` carry the Judge's
Stage 6 confidence notes forward — explicit empty arrays/`"none"` when there's nothing to
report, not omitted fields, so a later gate or stale-decision review can't mistake "wasn't
recorded" for "nothing was uncertain."

`review_by` is not optional: prior-art conclusions rot. A DEPEND verdict on a library with a
single maintainer should be re-checked sooner (3–6 months) than a VENDOR verdict on a small,
stable utility (12 months is fine). Pick the date at record time, not as an afterthought.

Stage 1 (Trigger) checks this file first, every time, before any lane runs — the `grep`/`cat`
invocation is in `SKILL.md` §0. A hunt whose registry entry hasn't hit `review_by` yet is cited,
not repeated. A stale entry gets re-validated starting at Stage 5 (Probe) on the previously
winning candidate only — not a full re-sweep from Stage 3.

## Revalidating a stale decision

A passed `review_by` means the evidence is old enough to recheck before citing again, not that
the verdict was wrong. `SKILL.md` §0 decides *whether* that means a targeted probe of the prior
winner or a fresh hunt from stage 0; this section shows what the resulting record looks like.
Both cases start from the same read: the prior ADR plus its registry line. It is a manual
write-up like any other ADR — no scheduler, controller, or automatic change-detector triggers it.

Compare the prior record against the current evidence, rights (license, ownership, terms), and
requirements. Then state: recommendation **retained** or **changed**, and any unresolved
uncertainty.

### Case A — framing holds, winner re-confirmed (targeted probe)

Problem, constraints, and exclusion criteria are unchanged, so re-probe only the previous winner
(stage 5). No new sweep or snowball.

```markdown
## Revalidation — ADR-3 (2027-01-22)

**Prior record:** ADR-3 (2026-07-19), registry id `adr-3`, DEPEND on `example-org/example-lib`.
**Trigger:** `review_by` 2027-01-19 passed.
**Changed since:** evidence only — license unchanged (MIT), 3 releases since the prior probe,
  no new advisories. Requirements and rights: unchanged.
**Recommendation:** retained — DEPEND on `example-org/example-lib`.
**Unresolved uncertainty:** the single-maintainer risk from ADR-3 still stands; not re-litigated.
**Why a targeted probe suffices:** only time changed. A full sweep would re-derive the same
  shortlist at far higher cost for no new information.
```

Append a superseding registry line; the original is never edited:

```json
{"id": "adr-3-revalidated-2027-01", "date": "2027-01-22", "problem": "<same as adr-3>",
 "vocabularies": ["..."], "verdict": "DEPEND", "candidate": "example-org/example-lib",
 "sources": ["gh:example-org/example-lib"],
 "confidence": "high", "degraded_lanes": [], "evidence_gaps": [], "unresolved_ambiguity": [],
 "review_by": "2027-07-22", "adr_path": "docs/adr/0003-....md",
 "supersedes": "adr-3", "delta": "winner re-confirmed, no framing change"}
```

### Case B — requirements changed, fresh hunt

A changed constraint (new compliance requirement, rights change, license change on the
incumbent) means the old question is no longer the one being asked: restart from stage 0
(Re-problem) and re-frame at stage 2, not stage 5.

```markdown
## Revalidation — ADR-7 (2027-02-03)

**Prior record:** ADR-7 (2026-06-01), registry id `adr-7`, VENDOR (reimplemented the idea
  rather than depend on an unlicensed prototype).
**Trigger:** `review_by` 2026-12-01 passed; the re-check also surfaced a new requirement — the
  consuming service now needs audit logging that the original problem never scoped.
**Changed since:** requirements. The original candidate is still unlicensed and unmaintained,
  which is moot given the new requirement.
**Recommendation:** changed — problem restated, fresh hunt run (ADR-9): a maintained
  Apache-2.0 candidate with built-in audit logging; verdict DEPEND.
**Unresolved uncertainty:** none carried forward; ADR-9's Judge stage records its own gaps.
**Why a fresh hunt:** ADR-7's exclusion criteria no longer match the ask; re-probing the old
  winner under them would answer a question nobody is asking.
```

The new hunt's registry line (`adr-9`) carries `"supersedes": "adr-7"`; ADR-7's line is untouched.

### Preserve either way

- Original ADR and registry line are never edited or deleted. The superseding line points
  backward (`supersedes`); no reverse link is written into the original.
- Keep `sources` and `review_by` (ADR Decision block and registry line) on every new record, and
  the privacy checks above: registry gitignored, ADR generic enough to publish.
- If a source from the original probe is unavailable now (dead link, private repo, deleted
  account), say so in the revalidation record rather than silently dropping it — an unreachable
  receipt is recorded uncertainty, not an omission.
- `scripts/sanitize_check.sh` applies as usual: no machine-specific paths, emails, or secrets.
