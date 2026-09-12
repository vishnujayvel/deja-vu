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
