# Exemplar: a decision that later changed

**Label:** real — re-encodes this repository's own published `docs/adr/0011-decision-taxonomy-compositional-packet.md`. No simulated data.

**Verdict:** BUILD (schema and record only) · **Confidence:** high on the taxonomy design, moderate on migration completeness · **Degraded lanes:** none · **Evidence gaps:** 31 pre-existing free-text registry entries are not yet backfilled

## Problem

This is the corpus's example of a decision revisited, not a first-time decision. deja-vu's own
decisions registry originally stored prior-art verdicts as free-form strings — an implicit
earlier decision that "a verdict is a string" was good enough. A registry audit found 31
recorded decisions using 12 distinct verdict strings, several of them composites like
`"DEPEND+BUILD"` that pack two different dispositions into one opaque token nothing downstream
could route, compare, or validate by machine.

## What changed, and why

Three status-quo-adjacent options were considered and rejected first (expand the enum to cover
composites, collapse to one composite score, keep free text with a style guide) — each one
either kept the same opacity or made it worse. The change that stuck: independent,
schema-validated dimensions per route component, composed into a packet
(`schemas/decision-packet.schema.json`), so a mixed outcome like "approved dependency, deferred
custom adapter" is representable without flattening it into one string.

What did **not** change: the validation mechanism. JSON Schema (draft 2020-12) via the
`jsonschema` library was chosen over hand-rolling a custom validator — itself a small `depend`
route component inside the same packet, alongside the larger `custom-build` component for the
taxonomy design itself. This is the schema's own "mixed packet" capability, demonstrated on a
real internal decision.

## Honest incompleteness

The migration is explicitly partial: existing free-text registry entries are not backfilled
into the new shape, and downstream tooling that reads only the free-text verdict is unaffected
for now. The packet's `uncertainty.residual` field states this directly rather than implying
the migration is finished.

## Receipts

- `docs/adr/0011-decision-taxonomy-compositional-packet.md` — full context, options
  considered, and consequences.
- `docs/design.md` §5.4 — the taxonomy this ADR made executable.
- `schemas/decision-packet.schema.json` — the resulting schema.
- `tests/test_decision_packet_schema.py` — the schema's own regression suite, run via
  `pytest tests/ -q`.
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json`.
