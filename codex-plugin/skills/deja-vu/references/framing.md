# Stage 2 — Framing

Prior art hides behind vocabulary. Search your solution's words and you will only ever find
things that describe themselves the way you would — which is a small, self-confirming slice of
what exists.

## Multi-vocabulary restatement

Write the problem 2–3 different ways, each in the vocabulary a **different community** would
use for it. Example — a spec-drift detector:

| Vocabulary | Restatement | Community it comes from |
|---|---|---|
| Testing | "doc-code sync checker" | test-infra engineers |
| Docs tooling | "living documentation tool" | technical writers |
| Contract-testing | "docs-as-tests framework" | API/contract-testing folks |

Four search strings, four different result sets — the tool that would have taken an hour to
build might already exist under a name none of your first instincts would produce. Do this
*before* dispatching any lane; every lane brief in `references/lanes.md` should carry all 2–3
restatements, not just the one that felt natural.

## Exclusion criteria — write them before you meet a candidate

Kitchenham's rule, ported from systematic-review methodology: decide what disqualifies a
candidate **before searching**, so a tempting hit cannot be rationalized in after the fact by
loosening the criteria to fit it. Write these down as a short checklist and keep them visible
through Sweep, Snowball, and Judge.

Template:

```
Problem (solution-free): <from Stage 0>
Vocabularies searched:    <2-3 restatements>

Exclusion criteria (pre-registered — do not edit once sweep starts):
- [ ] Unmaintained: no commits/release in the last <N> months
- [ ] License: <bucket(s) that disqualify — e.g. no-LICENSE, AGPL for a linked dependency>
- [ ] Scope mismatch: solves a superset/subset of the problem that doesn't compose cleanly
- [ ] Platform/language mismatch that can't be bridged cheaply
- [ ] Known health red flag: single-maintainer with no bus-factor, or a fork of an
      abandoned original with no divergence
- [ ] <problem-specific: anything domain knowledge already rules out>
```

If you find yourself editing this list mid-sweep to let a specific candidate through, stop —
that is the exact rationalization this stage exists to prevent. Add a note to the ADR instead
(`references/record.md`) explaining why a criterion was wrong, and fix it for *next* hunt.

Output of this stage feeds directly into Stage 3: every lane brief gets the vocabularies and
the exclusion criteria, verbatim.
