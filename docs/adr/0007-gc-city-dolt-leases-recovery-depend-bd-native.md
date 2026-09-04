# ADR 0007 — [relocated: out-of-scope host-infrastructure record]

**Status:** superseded-by-relocation

## What this was

This slot held a Gas City host-infrastructure incident record (a Dolt
schema-skew recovery on the shared `hq` database, affecting rigs `for-us`,
`bw2`, `sj`, `contour`, and `hw`). It is not a Deja Vu product decision — it
documents an outage in the operator's Gas Town control plane, a different
project with its own repository.

## Why it was removed from this repository

It was committed here by mistake (folded into commit `bdf8622`, "wip(p1):
snapshot v2.1 work products from the Codex session", 2026-09-04), and its
presence violated the Beads/memory ownership boundary recorded in
[ADR-12](0012-beads-privacy-memory-boundaries.md): this repository is scoped
to Deja Vu product development, not host-project or cross-rig operational
history. Part B of `deja-vu-v2.5.1` requires that no unrelated private
decision remain in this public skill repo's tracked files.

## Where the record lives

No evidence was deleted. The original ADR-0007 text (verdict, hunt summary,
decision, alternatives, consequences, sources) is fully preserved in this
repository's git history:

- Original authoring commit: `bef2440` ("docs(adr): ADR-0007 - DEPEND on
  bd-native migration for hq Dolt leases schema-skew")
- Carrier commit that brought it into this repo's tracked tree: `bdf8622`

It has not yet been re-filed as an ADR in the Gas City host control-plane
repository (the `vishnu-city` rig set) — that migration is host-project
follow-up work, outside this repository's scope and this bead's authority to
perform.

This stub exists only so the ADR-0007 numbering slot is not silently reused
for an unrelated future decision.
