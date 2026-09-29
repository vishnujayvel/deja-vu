# Stage 9 — Learn

The rubric only improves if verdicts get checked against what actually happened. This stage is
not part of a normal hunt — it runs on its own cadence, invoked deliberately (e.g. `/deja-vu
debrief`, or a periodic `/loop`), not as step 10 of every trigger.

## The debrief loop

For each entry in `data/decisions-registry.jsonl` old enough to have an outcome:

1. **If DEPEND/FORK/VENDOR**: did the adopted dependency survive? Was it abandoned, did a CVE
   land that changed the health picture, did the license change on you (a real and recurring
   risk), did the fence-check assumption hold or get violated by an update?
2. **If BUILD**: did the custom build prove necessary — or did prior art surface later that
   would have obviated it? Did the reversibility bet (Stage 6, point 6) turn out to be priced
   right?
3. **If NOT-A-PROBLEM/DIFFERENT-PROBLEM**: did the null solution or reframed problem actually
   hold up, or did the original need resurface later in a way that shows Stage 0 mis-scoped it?

Score each reviewed entry and append — never overwrite — to a calibration file,
`data/calibration.jsonl`.

**Protect it before the first append**, the same way `data/decisions-registry.jsonl` is
protected (`references/record.md`): run `git ls-files --error-unmatch data/calibration.jsonl`
(must exit `1` — untracked) and `git check-ignore data/calibration.jsonl` (must exit `0` —
ignored). If `check-ignore` exits `1` and no rule covers it yet, add the exact line
`/data/calibration.jsonl` to the host project's root `.gitignore` and re-run `check-ignore` to
confirm it now matches. If the file is already tracked, or protection can't be confirmed, don't
append — hand off to the human instead. Once protection is confirmed, every entry is an
immutable, provenance-bearing observation: a correction is a new line referencing the old one by
`registry_id`, never an edit to a line already written.

Separate **observed facts** — what happened, checkable against the world — from
**interpretation** — the retrospective read of what those facts mean for the original verdict.
Collapsing the two means a later re-read can't tell "this is what we saw" from "this is what we
concluded," which matters once a pattern gets proposed as a policy change (see below).

```json
{"registry_id": "adr-3", "reviewed_date": "2027-01-20", "original_verdict": "DEPEND",
 "outcome_kind": "abandonment",
 "outcome": "survived | abandoned | license-changed | proved-unnecessary | vindicated | ...",
 "source": "<who/what observed this, e.g. 'maintainer changelog', 'team retro 2027-01-18'>",
 "observed_at": "2027-01-18", "confidence": "high | moderate | low",
 "observed_facts": ["<checkable fact 1>", "<checkable fact 2>"],
 "interpretation": "<one paragraph: what this means for the original verdict — kept separate from the facts above>",
 "correct_in_hindsight": true}
```

`outcome_kind` is a fixed, low-cardinality vocabulary — pick the closest match, don't invent a
new one per entry:

| `outcome_kind` | Meaning |
|---|---|
| `success` | The decision held; no correction needed. |
| `failure` | The decision produced a bad outcome the original verdict didn't anticipate. |
| `abandonment` | An adopted dependency, or a built component, was later dropped. |
| `decision-reversal` | The decision itself was overturned (a DEPEND became a BUILD, etc.). |
| `unanticipated-custom-work` | Custom work had to be done anyway despite a non-BUILD verdict. |
| `measurement-gap` | There isn't enough evidence yet to score this entry. |

A `measurement-gap` record still counts as a debrief pass — appending one tells a future reader
"we looked and couldn't tell," which is different from silence, which reads as "we never looked."

## What future hunts do with this file

Future Judge stages (`references/judge.md`) load `data/calibration.jsonl` as worked examples —
the same case-law pattern used by taste-calibration systems: not a rule, but a precedent to weigh
against. A judge scoring a candidate against a maintainer who has, per the calibration file,
abandoned two prior adopted dependencies should weigh the health dimension accordingly.

## Turning a pattern into a policy proposal

One observation is an anecdote, not a signal — a single `measurement-gap` or a single
`abandonment` proves nothing about the doctrine. A policy proposal must cite a **cohort of
comparable observations**: multiple `calibration.jsonl` entries that share an `outcome_kind` and
a common thread in their `interpretation` fields, not one striking entry. List the cited
`registry_id`s in the proposal so the human can check the cohort, not just trust the summary.

## Cohort debriefs

A cohort debrief is a manual write-up over a handful of `calibration.jsonl` lines — no
database, service, or scheduler. It exists so a proposal rests on comparable cases, not on
whichever entry was most memorable.

**Cohort inclusion.** State the rule before listing members, using attributes already in the
registry and calibration lines: `outcome_kind`, `original_verdict`, the problem's vocabulary,
and an evidence attribute (e.g. a degraded lane, or a candidate with one maintainer). Entries
are comparable only if they match on every attribute the rule names. Don't pad a cohort with
near-matches, and don't drop a member because it complicates the story — a contrary entry that
fits the rule is a counterexample and gets listed (below).

**Descriptive measures — only where the evidence supports them.** Report counts, not a score;
never combine them into a single quality number. Each measure needs a numerator and
denominator drawn from cited entries, or it is omitted:

| Measure | Read from |
|---|---|
| Avoided builds | non-BUILD verdicts whose outcome was `success` |
| Evidence completeness | entries with empty `evidence_gaps` and `degraded_lanes` / all entries |
| Integration delta | extra integration work beyond the Stage 6 estimate, where an `observed_fact` records it |
| Reversal rate | `decision-reversal` entries / all entries |
| Revalidation value | revalidations (`references/record.md`) that changed the recommendation / all revalidations |

**Flag weak cohorts.** Say so in the debrief itself, not in a footnote, when:

- **Small** — fewer than about five comparable entries, so one entry moves any rate by 20+
  points. Report the counts and stop; do not propose.
- **Biased** — members share a selection effect: same maintainer or ecosystem, same reviewer,
  or only cases old enough to have an outcome (survivorship). Name the effect.
- **Missing data** — `measurement-gap` entries, or blank fields behind a measure. Count them
  separately from the denominator instead of dropping them.

### Example debrief and proposal

```markdown
## Cohort debrief — post-adoption license changes (2027-03-10)

**Inclusion rule:** `original_verdict` DEPEND, `outcome_kind` in {`abandonment`,
  `decision-reversal`}, interpretation cites a license or governance change.
**Members (6):** `adr-3`, `adr-5`, `adr-8`, `adr-11`, `adr-12`, `adr-14`.
**Observed** (checkable):
  - 6 of 14 DEPEND entries reviewed in this window match the rule.
  - Evidence completeness: 10 of 14 DEPEND entries had no `evidence_gaps`.
  - Reversal rate among DEPEND entries: 2 of 14 (`adr-5`, `adr-11`).
  - Integration delta: recorded in only 2 entries; not reported.
  - Missing data: `adr-6` is a `measurement-gap`, counted apart from the 14.
**Counterexamples:** `adr-2`, `adr-9` — DEPEND on candidates whose license stayed stable for the
  whole window; the pattern doesn't explain them.
**Limits:** n=14 total, 6 in the cohort — above the small-cohort line but thin. Only entries old enough to have an outcome are
  included (survivorship). Four of six members share one ecosystem (bias).
**Interpretation** (not observed): the health dimension may under-weight post-adoption license
  risk in that ecosystem.

## Proposal (not applied)

**Change:** in `references/judge.md`, weigh a candidate's license-change history in the health
  dimension.
**Cohort:** `adr-3`, `adr-5`, `adr-8`, `adr-11`, `adr-12`, `adr-14`. **Counterexamples:** `adr-2`, `adr-9`.
**Held-out check:** run `python3 evals/run_evals.py --offline` plus the next three hunts'
  shortlists through the changed Judge; the change fails if the `adr-2` or `adr-9` winner flips.
**Rollback:** revert the single commit; no registry or calibration line is edited.
**Decision:** a human, in a normal reviewed Git change — nothing here edits live policy.
```

A proposal states the cohort and its size, the supporting and counterexample `registry_id`s,
the limits above, a held-out check, and a rollback idea. A small cohort yields a debrief with no
proposal. Either way it is a write-up for a human; it changes nothing by itself.

## Sanitizable promotion fields

`calibration.jsonl` stays project-local — gitignored per the protection step above, never synced
or committed. If an entry is generalizable enough to promote into shared documentation (an
example in this file, a cross-project precedent), promote only `outcome_kind`, `confidence`,
`correct_in_hindsight`, and a rewritten `interpretation` stripped of project-identifying detail.
Never promote `source`, raw `observed_facts`, or `registry_id` verbatim — they routinely carry
maintainer names, internal paths, or other project-specific identifiers. Run
`scripts/sanitize_check.sh` on anything promoted, the same public-repo hygiene gate the rest of
this repo uses.

## The one hard rule

**This stage never edits `SKILL.md`, or any file under `references/`, on its own.** The
calibration file is evidence; a human reads it and decides whether the doctrine itself should
change. If a debrief surfaces a pattern strong enough to justify changing how the skill hunts —
"we keep under-weighting license changes post-adoption" — write that up as a cohort-backed
proposal (see above) and hand it to the human explicitly. Do not fold it into the router quietly
because it seemed obviously correct; that is the same rubber-stamp failure mode the Gate (Stage
7) exists to prevent, one level up. No observation, or count of observations, ever mutates
`SKILL.md`, a reference doc, or the router automatically — a human always makes that call.
