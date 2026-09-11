# Counterexample: a good design fit blocked from fork/vendor by rights

**Label:** real — a facet of deja-vu's own founding hunt (`docs/design.md` §6, footnote 1), isolated here to demonstrate the schema's rights dimension specifically. No simulated data.

**Verdict:** BUILD, route `clean-room-reimplement` · **Confidence:** high · **Degraded lanes:** none · **Evidence gaps:** whether an unpublished license grant exists is unconfirmed and was not chased

## Problem

`trelmitt/claude-skills`' `build-vs-borrow` is the single closest prior-art candidate to
deja-vu's own pipeline design — verified hands-on to run clean, with a real 8-stage
DETECT→…→RECORD pipeline, a working sweep script, a 4-verdict model, and an ADR template.
A strong fit on its own would normally push toward FORK. It doesn't, because of rights.

## Reasoning path — why fit alone doesn't decide the route

1. **Judge → License.** `references/judge.md`'s "No-LICENSE trap": no LICENSE file means all
   rights reserved. You may read it and learn from it; you may not fork or vendor it. This is
   a hard disqualifier, not a yellow flag, independent of code quality.
2. **Schema rule 4** (`schemas/decision-packet.schema.json`, ADR-11): a route component whose
   `rights` is `prohibited` or `unknown` can never select `route: fork` or
   `route: vendor-source` — the rights dimension structurally gates the route dimension,
   rather than leaving it to reviewer discretion.
3. **Schema rule 2**: `route: clean-room-reimplement` forces `custom_behavior: true`, which in
   turn forbids `authority: agent-authorized` — a human had to sign off on this route, not an
   agent, even though the underlying design was well-understood and low-risk on its own merits.
4. **Resolution**: adopt the *design* (pipeline stages, verdict vocabulary) as a documented
   reference, reimplement independently, attribute the lineage in `docs/design.md` §6. No
   source lines or literal text were copied.

## Receipts

- `gh api repos/trelmitt/claude-skills` re-verified 2026-09-11: `license: null` — confirms
  the no-LICENSE fact independently, seven weeks after the original citation.
- `docs/design.md` §6 footnote 1: "No LICENSE file — all rights reserved — and an anonymous
  author, so its code was not forked; its designs were treated as a reference and
  reimplemented."
- `references/judge.md` § License, "No-LICENSE trap."
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json` — exercises schema rules 2, 3, and 4 with a real
  (not synthetic) candidate.
