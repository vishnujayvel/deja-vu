# Counterexample: a good design fit blocked from fork/vendor by unresolved rights

**Label:** real — a facet of deja-vu's own founding hunt (`docs/design.md` §6, footnote 1), isolated here to demonstrate the schema's rights dimension specifically. No simulated data.

**Verdict:** BUILD, route `clean-room-reimplement` · **Confidence:** moderate · **Degraded lanes:** none · **Evidence gaps:** no explicit grant or restriction found; whether one exists outside the repository is unconfirmed

## Correction from an earlier draft of this entry

An earlier version of this receipt used `rights: prohibited` based solely on GitHub's
automated Licensee match returning `null`. That overstates what was actually confirmed.
Per `docs/adr/0011-decision-taxonomy-compositional-packet.md`, an unlicensed candidate maps to
`rights: unknown` by default (no grant discovered); `prohibited` requires the hunt to confirm
no grant exists via something explicit — an all-rights-reserved notice, or terms that
explicitly forbid redistribution. Silence is not that confirmation. This entry now uses
`rights: unknown`, and the route (`clean-room-reimplement`) is unchanged, because the schema's
rule 4 blocks `fork`/`vendor-source` under `unknown` exactly as it does under `prohibited` —
the correction changes the stated certainty, not the actual route taken.

`evidence_level` was also downgraded from `operational` to `source-inspected`: reading a
repository's license status is a source inspection, not a hands-on operational test.

## Problem

`trelmitt/claude-skills`' `build-vs-borrow` is the single closest prior-art candidate to
deja-vu's own pipeline design — a real 8-stage DETECT→…→RECORD pipeline, a working sweep
script, a 4-verdict model, and an ADR template, which `docs/design.md` records as having been
verified hands-on by an earlier hunt. A strong fit on its own would normally push toward FORK.
It doesn't, because the rights question was never resolved.

## Reasoning path — why fit alone doesn't decide the route

1. **Judge → License.** `references/judge.md`'s "No-LICENSE trap": no LICENSE file means the
   default assumption is all rights reserved. You may read it and learn from it; you may not
   fork or vendor it without more.
2. **This corpus entry's own check (2026-09-11).** GitHub's Licensee reports no LICENSE file;
   a direct read of the repository's root listing and `README.md` confirms no LICENSE file and
   no license/rights/copyright text anywhere. The repository is silent, not explicit — no
   all-rights-reserved notice was found either.
3. **ADR-11's rights taxonomy.** Silence without an explicit restriction is `unknown`, not
   `prohibited`. Both values are treated the same by the schema's rule 4 (neither permits
   `fork`/`vendor-source`), so the practical route doesn't change — but conflating them
   overstates confidence that isn't there.
4. **Schema rule 2**: `route: clean-room-reimplement` forces `custom_behavior: true`, which in
   turn forbids `authority: agent-authorized` — a human had to sign off on this route, not an
   agent, even though the underlying design was well-understood and low-risk on its own merits.
5. **Resolution**: adopt the *design* (pipeline stages, verdict vocabulary) as a documented
   reference, reimplement independently, attribute the lineage in `docs/design.md` §6. No
   source lines or literal text were copied.

## Receipts

- `gh api repos/trelmitt/claude-skills` re-verified 2026-09-11: `license: null`.
- `gh api repos/trelmitt/claude-skills/contents` and `contents/README.md`, read directly
  2026-09-11: no LICENSE file in the root listing; no license/rights/copyright text in the
  README.
- `https://docs.github.com/en/rest/licenses/licenses` — Licensee's matching scope and its
  explicit "not legal advice" caveat, verified 2026-09-11.
- `docs/design.md` §6 footnote 1: "No LICENSE file — all rights reserved — and an anonymous
  author, so its code was not forked; its designs were treated as a reference and
  reimplemented" — cited as that document's own characterization, not repeated here as this
  entry's independently verified legal conclusion.
- `docs/adr/0011-decision-taxonomy-compositional-packet.md` — the unknown-vs-prohibited rule
  this entry now follows.
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json` — exercises schema rules 2 and 4 with a real
  (not synthetic) candidate.
