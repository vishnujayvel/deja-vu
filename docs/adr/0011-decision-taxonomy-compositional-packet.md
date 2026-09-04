# ADR-11: Multidimensional decision taxonomy as a compositional packet, not an overloaded verdict enum

**Date:** 2026-09-04
**Status:** accepted

## Context

The registry stores prior-art decisions as free-form verdict strings. An audit of the
existing registry found 31 recorded decisions using 12 distinct verdict strings, several
of them composites such as "DEPEND+BUILD" that pack two different dispositions — reuse a
dependency for part of a problem, and custom-build the rest — into one opaque token. A
composite string like that cannot be routed, compared, or validated by machine: nothing
distinguishes "the dependency route is approved and the custom adapter is still pending
human review" from "the whole thing is approved" except a human re-reading the prose.

`docs/design.md` §5.4 already specifies the target model in prose: a proposed decision
packet with an ordered `route_components` array, nine independent dimensions (need
disposition, prior-art kind, candidate fit, rights and policy, evidence level, reuse
route, custom delta, uncertainty, and authority) applied at packet or component scope,
and an authorized decision record that references the immutable proposed packet plus
authority receipts. That prose was not executable — nothing in the repository enforced
its shape. This decision makes it executable without redesigning it.

## Options considered

| Candidate | Why it lost / won |
|---|---|
| Expand the six-value verdict enum (`NOT-A-PROBLEM`, `DIFFERENT-PROBLEM`, `DEPEND`, `FORK`, `VENDOR`, `BUILD`) to cover composites | Grows without bound as new composite shapes appear (`DEPEND+BUILD`, `FORK+VENDOR`, ...); still a single string, so nothing prevents a new ad hoc composite from re-introducing the same opacity |
| One composite numeric or categorical score | Hides which specific dimension (rights vs. evidence vs. authority) drove the score; not queryable per-component, and two packets with the same score can have opposite risk profiles |
| Keep free text with a style guide | Non-machine-checkable by construction; the existing 12-string sprawl is the direct result of exactly this approach |
| **Independent, schema-validated dimensions per route component, composed into a packet (chosen)** | Matches `docs/design.md` §5.4 exactly; each dimension is independently queryable and each route component carries its own authority state, so a mixed packet (approved dependency + deferred custom adapter) is representable without flattening |

## Decision

**Verdict:** BUILD (schema and record only — this ADR adds no runtime code path)

Add `schemas/decision-packet.schema.json` (JSON Schema draft 2020-12) as the executable
contract for the packet §5.4 describes:

- A `stage` discriminator distinguishes the immutable `proposed` packet (hashed into
  `approval_material_sha256`, which excludes authority decisions and receipt references)
  from the `authorized` decision record (adds `proposed_packet_ref`, `authority_receipts`,
  `executable_component_ids`, and its own `decision_record_sha256`), matching §5.4's
  no-circular-hash requirement structurally rather than by convention.
- The nine dimensions are placed at the scope §5.4 assigns them: `need_disposition` and
  packet-level `uncertainty` at packet scope; `prior_art_kind` on each candidate
  comparison; `fit`, `rights`, `evidence_level`, `route` (reuse route), `custom_behavior`
  / `custom_delta`, per-component `residual_uncertainty`, and `authority` on each
  `route_components` entry.
- Packet-validation rules from §5.4's closing paragraph are encoded as schema
  constraints, not left to reviewer discretion: a component missing a stable ID,
  evidence, output boundary, or authority state fails `required`; custom behavior cannot
  carry `authority: agent-authorized` (`clean-room-reimplement` and `custom-build` are
  both forced to `custom_behavior: true`, which in turn forbids `agent-authorized` —
  `custom-build` is definitionally custom behavior per the `reuse_route` enum, so it
  gets the same forcing rule as `clean-room-reimplement` rather than being able to
  carry `custom_behavior: false` under `agent-authorized`); a component
  with `rights: prohibited` cannot carry `authority: approved` or `agent-authorized`;
  (rule 4) a component whose `rights` is `prohibited` or `unknown` cannot carry
  `route: fork` or `route: vendor-source`; and (rule 5) a `stage: proposed` packet
  cannot carry post-resolution authority outcomes (`approved`, `rejected`, `deferred`)
  on any `route_components` entry, since those outcomes are only meaningful once an
  authority receipt exists — a `proposed` packet may only declare the pre-resolution
  states `agent-authorized` or `human-required`.
- **Rule 4 and the "unlicensed" gap.** `rights` (`§5.4`'s "rights and policy" dimension)
  has four values: `permitted`, `conditional`, `prohibited`, `unknown`. There is no
  literal `unlicensed` value — "unlicensed source" is a fact about the candidate
  (no license grant was found), not a distinct point in this dimension, and it maps to
  one of the two values that already deny forking/vendoring: `unknown` when the
  hunt has not verified whether a grant exists (the default for a candidate with no
  discovered license), and `prohibited` once the hunt confirms no grant exists (e.g. an
  explicit all-rights-reserved notice, or a license whose terms forbid the redistribution
  `fork`/`vendor-source` would require). `conditional` is deliberately excluded from rule
  4: a conditional grant (e.g. attribution-only, non-commercial) still confers some reuse
  right, so §5.4's "source without reuse rights ... cannot be forked or vendored" does not
  apply to it — the `policy_clauses` obligations carry the condition instead. This closes
  the licensing/rights boundary docs/design.md draws at §5.4 ("source without reuse rights
  may inform an idea, but it cannot be forked or vendored"): before rule 4, only the
  *authority* on a prohibited/unknown-rights component was constrained (rule 3), so a
  packet could still select `route: fork` or `route: vendor-source` for that component and
  merely leave `authority` unresolved — the rights dimension never actually gated the
  route dimension. Rule 4 makes that gate structural: `fork` and `vendor-source` are
  unreachable route values whenever rights are prohibited or unverified, independent of
  what authority state is later attempted.
- `authority_receipts` entries mirror the authority-receipt field list in §6 of
  `docs/design.md` (stable receipt ID, authenticated principal, issuer and auth method,
  project/hunt IDs, policy version, `approval_material_sha256`, exact component IDs and
  hashes, decision, nonce, issued/expiry times, issuer key ID, signature) so the receipt
  shape and the packet shape are validated by the same schema family.

This is additive: `evals/run_evals.py`'s `VALID_VERDICTS` and the existing six-value
verdict field are untouched. The human-readable verdict string may keep saying "DEPEND"
or "BUILD" per §6 — the typed packet and its route components are the source of truth
this ADR makes checkable, and migrating callers off the free-text verdict is future work,
not part of this change.

`contracts/module-contracts.json` gets one new entry so the schema falls under the
Fable review gate like every other governed JSON contract.

## Consequences

- A decision packet can now represent "approved dependency, deferred custom adapter" as
  two `route_components` entries with independent `authority` values, instead of forcing
  a single composite verdict string.
- `approval_material_sha256` can be computed and checked mechanically once a canonical
  serialization is implemented (not part of this change) because the schema fixes exactly
  which fields are covered (`problem_disposition`, `candidate_comparisons`, `uncertainty`,
  `reversibility`, `route_components`) and excludes authority/receipt fields at the
  `proposed` stage.
- Downstream tooling that currently reads only the free-text verdict is unaffected; it
  can adopt the packet schema incrementally per hunt.

## Review trigger

Re-validate if `docs/design.md` §5.4 or §6 changes the dimension list, the packet/record
split, or the authority-receipt field list; or if a real hunt produces a packet shape the
schema rejects for a reason that isn't one of the five validation rules stated in or
derived from §5.4 (the first three from its closing paragraph; rule 4 structurally
encodes its "source without reuse rights ... cannot be forked or vendored" sentence,
added after a Fable review found the rights dimension never constrained the route
dimension — see `deja-vu-v2.32`; rule 5 closes a second Fable re-review gap where
`custom-build` could hide custom behavior under `agent-authorized` and a `proposed`
packet could pre-bake post-resolution authority outcomes — see `deja-vu-v2.2.1`).

## Receipts

- Registry audit (existing note on `deja-vu-v2.2`): 31 decisions, 12 distinct verdict
  strings, multiple `DEPEND`+`BUILD`-style composites.
- `docs/design.md` §5.4 (lines ~340–384): dimension table, packet/record split, and the
  three packet-validation rules this schema encodes.
- `docs/design.md` §6 (lines ~506–517): authority receipt field list mirrored in
  `$defs/authority_receipt`.
- `schemas/decision-packet.schema.json` validated against the Draft 2020-12 meta-schema:
  `python3 -c "import json,jsonschema;jsonschema.Draft202012Validator.check_schema(json.load(open('schemas/decision-packet.schema.json')))"`.
